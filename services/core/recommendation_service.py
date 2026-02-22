from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from sqlmodel import Session, select
from models import User, MenuItem, PopulationStats, RecommendationSession, RecommendationFeedback, UserOrderHistory, BayesianTasteProfile
from models.query import ParsedQuery
from services.features.features import cosine_similarity, has_allergen, violates_diet
from services.features.gpt_helper import generate_rationale
from services.core.retrieval_service import RetrievalService
from services.core.reranking_service import RerankingService, RecommendationContext
from services.ml.ml_reranking_service import MLRerankingService
from services.explanation.explanation_service import ExplanationService
from services.context.context_enhancement_service import ContextEnhancementService
from services.learning.in_session_learning_service import InSessionLearningService
from services.composition.meal_composition_service import MealCompositionService
from services.explanation.explanation_enhancement_service import ExplanationEnhancementService
from services.user.interaction_history_service import InteractionHistoryService
from services.evaluation.confidence_service import ConfidenceService
from services.composition.query_service import QueryParsingService
from services.diversity.mmr_service import MMRService, DiversityConstraints
from services.diversity.cross_encoder_service import CrossEncoderService
from services.core.session_service import RecommendationSessionService
from services.learning.bayesian_profile_service import BayesianProfileService
from config.settings import settings
import math
from datetime import datetime
from utils.logger import setup_logger

logger = setup_logger(__name__)


def time_decay_score(ts: Optional[datetime], half_life_days: int) -> float:
    if not ts:
        return 1.0
    days = (datetime.utcnow() - ts).days
    return 0.5 ** (days / max(1, half_life_days))


class RecommendationService:
    def __init__(self, use_new_pipeline: bool = True, use_ml_reranking: bool = True):
        self.use_new_pipeline = use_new_pipeline
        self.use_ml_reranking = use_ml_reranking
        self.retrieval_service = RetrievalService() if use_new_pipeline else None
        self.reranking_service = None
        self.ml_reranking_service = None
        self.explanation_service = ExplanationService() if use_new_pipeline else None
        self.context_service = ContextEnhancementService()
        self.in_session_learning = InSessionLearningService()
        self.meal_composition = MealCompositionService()
        self.explanation_enhancement = ExplanationEnhancementService()
        self.interaction_history_service = InteractionHistoryService()
        self.confidence_service = ConfidenceService()
        self.query_parsing_service = QueryParsingService()
        self.mmr_service = MMRService()
        self.cross_encoder_service = CrossEncoderService()
        self.bayesian_profile_service = BayesianProfileService()
    
    def recommend(
        self,
        session: Session,
        user: User,
        restaurant_id: Optional[str] = None,
        top_n: int = 10,
        budget: Optional[float] = None,
        time_of_day: Optional[str] = None,
        mood: Optional[str] = None,
        occasion: Optional[str] = None,
        course_preference: Optional[str] = None
    ) -> Dict[str, Any]:
        if self.use_new_pipeline:
            return self._recommend_new_pipeline(
                session, user, restaurant_id, top_n,
                budget, time_of_day, mood, occasion, course_preference
            )
        else:
            return self._recommend_legacy(
                session, user, restaurant_id, top_n,
                budget, time_of_day
            )
    
    def _recommend_new_pipeline(
        self,
        session: Session,
        user: User,
        restaurant_id: Optional[str],
        top_n: int,
        budget: Optional[float],
        time_of_day: Optional[str],
        mood: Optional[str],
        occasion: Optional[str],
        course_preference: Optional[str] = None
    ) -> Dict[str, Any]:
        logger.info(
            "Generating recommendations with new pipeline",
            extra={
                "user_id": str(user.id),
                "restaurant_id": restaurant_id,
                "top_n": top_n,
                "course_preference": course_preference
            }
        )
        
        try:
            candidates = self.retrieval_service.retrieve_candidates(
                session=session,
                user=user,
                k=max(top_n * 3, 30),
                restaurant_id=restaurant_id,
                budget=budget,
                course_filter=course_preference,
                time_of_day=time_of_day
            )
        except Exception as e:
            logger.error(
                "Retrieval failed, falling back to legacy",
                extra={"error": str(e)},
                exc_info=True
            )
            return self._recommend_legacy(
                session, user, restaurant_id, top_n, budget, time_of_day
            )
        
        if not candidates:
            return {"items": [], "warnings": ["no_safe_items"]}
        
        pop_stats = session.exec(select(PopulationStats)).first()
        
        # Use ML reranking if enabled and model available
        if self.use_ml_reranking:
            if not self.ml_reranking_service:
                self.ml_reranking_service = MLRerankingService(population_stats=pop_stats)
            
            context = RecommendationContext(
                time_of_day=time_of_day,
                budget=budget,
                mood=mood,
                occasion=occasion,
                course_preference=course_preference
            )
            
            logger.info("Using ML reranking service")
            ranked_items = self.ml_reranking_service.rerank(
                candidates=candidates,
                user=user,
                context=context,
                session=session,
                top_n=top_n
            )
        else:
            # Fall back to rule-based reranking
            if not self.reranking_service:
                self.reranking_service = RerankingService(population_stats=pop_stats)
            
            context = RecommendationContext(
                time_of_day=time_of_day,
                budget=budget,
                mood=mood,
                occasion=occasion,
                course_preference=course_preference
            )
            
            logger.info("Using rule-based reranking service")
            ranked_items = self.reranking_service.rerank(
                candidates=candidates,
                user=user,
                context=context,
                top_n=top_n
            )
        
        context_dict = {
            "time_of_day": time_of_day,
            "budget": budget,
            "mood": mood,
            "occasion": occasion
        }
        explanations = self.explanation_service.generate_explanations(
            ranked_items=ranked_items,
            user=user,
            context=context_dict
        )
        
        results = []
        for ranked_item, explanation in zip(ranked_items, explanations):
            item = ranked_item.item
            user_sorted = sorted(
                user.taste_vector.items(),
                key=lambda kv: kv[1],
                reverse=True
            )
            matched = [
                k for k, v in user_sorted
                if item.features.get(k, 0.0) > 0.5
            ][:3]
            
            results.append({
                "item_id": str(item.id),
                "name": item.name,
                "score": round(ranked_item.final_score, 3),
                "matched_axes": matched,
                "reason": explanation,
                "safety_flags": [],
                "cuisine": item.cuisine,
                "price": item.price,
                "confidence": ranked_item.confidence,
                "provenance": {
                    "source": item.provenance.get("source", "ingested"),
                    "inference_confidence": item.inference_confidence
                },
                "ranking_factors": {
                    k: round(v, 3)
                    for k, v in ranked_item.ranking_factors.items()
                }
            })
        
        logger.info(
            "Recommendations generated successfully",
            extra={"user_id": str(user.id), "result_count": len(results)}
        )
        
        return {"items": results}
    
    def recommend_from_query(
        self,
        session: Session,
        user: User,
        query: str,
        top_n: int = 10,
        budget: Optional[float] = None,
        diversity_weight: float = 0.3,
        use_cross_encoder: bool = False,
        diversity_constraints: Optional[DiversityConstraints] = None
    ) -> Dict[str, Any]:
        if not query:
            raise ValueError("query cannot be empty")
        
        if not self.use_new_pipeline:
            raise ValueError("query-based recommendations require new pipeline (use_new_pipeline=True)")
        
        logger.info(
            "Generating query-based recommendations",
            extra={
                "user_id": str(user.id),
                "query": query,
                "top_n": top_n,
                "diversity_weight": diversity_weight,
                "use_cross_encoder": use_cross_encoder
            }
        )
        
        try:
            parsed_query = self.query_parsing_service.parse_query(query)
            
            logger.info(
                "Query parsed",
                extra={
                    "intent": parsed_query.intent.value,
                    "modifiers": [m.value for m in parsed_query.modifiers]
                }
            )
            
            candidates = self.retrieval_service.retrieve_candidates_from_query(
                session=session,
                user=user,
                parsed_query=parsed_query,
                k=max(top_n * 3, 50),
                budget=budget
            )
            
            if not candidates:
                return {
                    "items": [],
                    "warnings": ["no_candidates_found"],
                    "query_info": {
                        "raw_query": query,
                        "intent": parsed_query.intent.value,
                        "modifiers": [m.value for m in parsed_query.modifiers]
                    }
                }
            
            if use_cross_encoder and self.cross_encoder_service.is_available:
                logger.info("Applying cross-encoder reranking")
                scored_candidates = self.cross_encoder_service.rerank_parsed_query_results(
                    parsed_query=parsed_query,
                    candidates=candidates,
                    top_k=min(len(candidates), top_n * 2)
                )
                candidates = [item for item, score in scored_candidates]
            
            if diversity_weight > 0:
                logger.info("Applying MMR diversity reranking")
                final_items = self.mmr_service.rerank_with_mmr(
                    candidates=candidates,
                    user_taste_vector=user.taste_vector,
                    k=top_n,
                    diversity_weight=diversity_weight,
                    constraints=diversity_constraints
                )
            else:
                final_items = candidates[:top_n]
            
            results = []
            for item in final_items:
                item_data = {
                    "item_id": str(item.id),
                    "name": item.name,
                    "description": item.description,
                    "course": item.course,
                    "price": item.price,
                    "cuisine": item.cuisine,
                    "dietary_tags": item.dietary_tags,
                    "features": item.features,
                    "explanation": f"Matches your query: {query}"
                }
                results.append(item_data)
            
            logger.info(
                "Query-based recommendations generated successfully",
                extra={
                    "user_id": str(user.id),
                    "query": query,
                    "result_count": len(results)
                }
            )
            
            return {
                "items": results,
                "query_info": {
                    "raw_query": query,
                    "intent": parsed_query.intent.value,
                    "modifiers": [m.value for m in parsed_query.modifiers],
                    "cuisine_filter": parsed_query.cuisine_filter,
                    "taste_adjustments": parsed_query.taste_adjustments
                },
                "diversity_score": self.mmr_service._compute_diversity_score(final_items) if diversity_weight > 0 else None
            }
            
        except Exception as e:
            logger.error(
                "Query-based recommendation failed",
                extra={"error": str(e), "query": query},
                exc_info=True
            )
            raise
    
    def _recommend_legacy(
        self,
        session: Session,
        user: User,
        restaurant_id: Optional[str],
        top_n: int,
        budget: Optional[float],
        time_of_day: Optional[str]
    ) -> Dict[str, Any]:
        logger.info("Using legacy recommendation pipeline")
        
        q = select(MenuItem)
        if restaurant_id:
            from uuid import UUID
            q = q.where(MenuItem.restaurant_id == UUID(restaurant_id))
        items: List[MenuItem] = session.exec(q).all()

        # 2) hard filters
        safe: List[MenuItem] = []
        user_all = set(map(str.lower, user.allergies))
        for it in items:
            # explicit allergens list check
            if user_all.intersection(set(map(str.lower, it.allergens))):
                continue
            # deterministic ingredient mapping check
            if has_allergen(user.allergies, it.ingredients, explicit_allergens=it.allergens):
                continue
            if violates_diet(user.dietary_rules, it.dietary_tags):
                continue
            if budget is not None and it.price is not None and it.price > budget:
                continue
            safe.append(it)

        if not safe:
            return {"items": [], "warnings": ["no_safe_items"]}

        # 3) scoring
        pop = session.exec(select(PopulationStats)).first()
        pop_global = pop.item_popularity_global if pop else {}
        pop_rest = pop.item_popularity_by_restaurant if pop else {}

        def cuisine_aff(it: MenuItem) -> float:
            return max((user.cuisine_affinity.get(c, 0.0) for c in it.cuisine), default=0.0)

        def popularity(it: MenuItem) -> float:
            base = pop_global.get(str(it.id), 0.0) + pop_rest.get(str(it.restaurant_id), 0.0)
            return min(1.0, base)

        base_scores: Dict[str, float] = {}
        for it in safe:
            s = cosine_similarity(user.taste_vector, it.features)
            s += settings.LAMBDA_CUISINE * cuisine_aff(it)
            s += settings.LAMBDA_POP * popularity(it)
            # liked/disliked penalties
            if any(ing in set(map(str.lower, user.disliked_ingredients)) for ing in map(str.lower, it.ingredients)):
                s -= 0.1
            if any(ing in set(map(str.lower, user.liked_ingredients)) for ing in map(str.lower, it.ingredients)):
                s += 0.05
            # provenance discount
            if it.provenance.get("source") == "gpt_inferred":
                conf = it.inference_confidence or 0.5
                s *= (1.0 - settings.GPT_CONFIDENCE_DISCOUNT * (1.0 - conf))
            base_scores[str(it.id)] = max(0.0, min(1.0, s))

        # 5) diversification (MMR)
        selected: List[MenuItem] = []
        selected_ids: set = set()
        alpha = settings.MMR_ALPHA
        feats = {str(it.id): it.features for it in safe}
        while len(selected) < min(top_n, len(safe)):
            best_item = None
            best_score = -math.inf
            for it in safe:
                if str(it.id) in selected_ids:
                    continue
                diversity_penalty = 0.0
                if selected:
                    max_sim = max(cosine_similarity(feats[str(it.id)], feats[str(s.id)]) for s in selected)
                    diversity_penalty = (1 - alpha) * max_sim
                cand = alpha * base_scores[str(it.id)] - diversity_penalty
                if cand > best_score:
                    best_score = cand
                    best_item = it
            if not best_item:
                break
            selected.append(best_item)
            selected_ids.add(str(best_item.id))

        # 6) explainability
        results = []
        for it in selected:
            # matched axes: top positive contribution axes from item where user prefers high
            user_sorted = sorted(user.taste_vector.items(), key=lambda kv: kv[1], reverse=True)
            matched = [k for k, v in user_sorted if it.features.get(k, 0.0) > 0.5][:3]
            reason = generate_rationale({
                "user_axes": {k: user.taste_vector[k] for k in matched},
                "ingredients": it.ingredients,
                "cuisine": it.cuisine,
            }) or "Matched your tastes and restrictions."
            results.append({
                "item_id": str(it.id),
                "name": it.name,
                "score": round(base_scores[str(it.id)], 3),
                "matched_axes": matched,
                "reason": reason,
                "safety_flags": [],
                "cuisine": it.cuisine,
                "price": it.price,
                "confidence": it.inference_confidence,
                "provenance": {"source": it.provenance.get("source", "ingested"), "inference_confidence": it.inference_confidence},
            })

        return {"items": results}
    
    def recommend_with_session(
        self,
        session: Session,
        user: User,
        recommendation_session: RecommendationSession,
        top_n: int = 10,
        iteration: int = 1
    ) -> Dict[str, Any]:
        logger.info(
            "Session-based recommendation starting",
            extra={
                "session_id": str(recommendation_session.id),
                "user_id": str(user.id),
                "meal_intent": recommendation_session.meal_intent,
                "iteration": iteration
            }
        )
        
        from uuid import UUID as UUIDType
        restaurant_id_str = str(recommendation_session.restaurant_id)
        
        q = select(MenuItem).where(MenuItem.restaurant_id == UUIDType(restaurant_id_str))
        all_items: List[MenuItem] = session.exec(q).all()
        
        safe: List[MenuItem] = []
        user_all = set(map(str.lower, user.allergies))
        
        filtered_counts = {
            "allergen": 0,
            "diet": 0,
            "budget": 0,
            "session_excluded": 0,
            "permanently_excluded": 0
        }
        
        logger.info(
            "Starting safety filtering",
            extra={
                "user_id": str(user.id),
                "session_id": str(recommendation_session.id),
                "total_items": len(all_items),
                "user_allergies": list(user.allergies),
                "user_dietary_rules": list(user.dietary_rules),
                "session_excluded_count": len(recommendation_session.excluded_items),
                "permanently_excluded_count": len(user.permanently_excluded_items)
            }
        )
        
        for it in all_items:
            if user_all.intersection(set(map(str.lower, it.allergens))):
                filtered_counts["allergen"] += 1
                continue
            if has_allergen(user.allergies, it.ingredients, explicit_allergens=it.allergens):
                filtered_counts["allergen"] += 1
                continue
            if violates_diet(user.dietary_rules, it.dietary_tags):
                filtered_counts["diet"] += 1
                continue
            if recommendation_session.budget and it.price and it.price > recommendation_session.budget * 1.2:
                filtered_counts["budget"] += 1
                continue
            
            item_id_str = str(it.id)
            if item_id_str in recommendation_session.excluded_items:
                filtered_counts["session_excluded"] += 1
                continue
            
            if item_id_str in user.permanently_excluded_items:
                filtered_counts["permanently_excluded"] += 1
                continue
            
            safe.append(it)
        
        logger.info(
            "Safety filtering completed",
            extra={
                "user_id": str(user.id),
                "session_id": str(recommendation_session.id),
                "initial_count": len(all_items),
                "safe_count": len(safe),
                "filtered_by_allergen": filtered_counts["allergen"],
                "filtered_by_diet": filtered_counts["diet"],
                "filtered_by_budget": filtered_counts["budget"],
                "filtered_by_session_exclusion": filtered_counts["session_excluded"],
                "filtered_by_permanent_exclusion": filtered_counts["permanently_excluded"]
            }
        )
        
        if not safe:
            logger.warning(
                "No safe items after filtering",
                extra={
                    "user_id": str(user.id),
                    "session_id": str(recommendation_session.id),
                    "filtered_counts": filtered_counts
                }
            )
            return {"items": [], "warnings": ["no_safe_items"]}
        
        # Skip time filtering for intents that need items from all time periods:
        # - full_meal: needs appetizer + main + dessert (dessert blocked during breakfast)
        # - dessert_only/beverage_only: can be consumed anytime
        # Apply time filtering only for single-course intents that should match time of day
        skip_time_filter_intents = ["full_meal", "dessert_only", "beverage_only"]
        apply_strict_time_filter = recommendation_session.meal_intent not in skip_time_filter_intents
        
        time_filtered = self.context_service.apply_hard_time_filters(
            safe,
            recommendation_session.detected_hour,
            strict=apply_strict_time_filter
        )
        
        logger.info(
            "Time filtering completed",
            extra={
                "user_id": str(user.id),
                "session_id": str(recommendation_session.id),
                "before_count": len(safe),
                "after_count": len(time_filtered),
                "filtered_count": len(safe) - len(time_filtered),
                "time_of_day": recommendation_session.time_of_day,
                "detected_hour": recommendation_session.detected_hour,
                "strict_filtering": apply_strict_time_filter
            }
        )
        
        intent_filtered = self.context_service.apply_meal_intent_filters(
            time_filtered,
            recommendation_session.meal_intent,
            recommendation_session.hunger_level
        )
        
        logger.info(
            "Intent filtering completed",
            extra={
                "user_id": str(user.id),
                "session_id": str(recommendation_session.id),
                "before_count": len(time_filtered),
                "after_count": len(intent_filtered),
                "filtered_count": len(time_filtered) - len(intent_filtered),
                "meal_intent": recommendation_session.meal_intent,
                "hunger_level": recommendation_session.hunger_level
            }
        )
        
        order_history = session.exec(
            select(UserOrderHistory).where(UserOrderHistory.user_id == user.id)
        ).all()
        
        scored_with_penalty = self.context_service.apply_repeat_penalty(
            intent_filtered,
            order_history,
            days_threshold=30
        )
        
        candidates = [item for item, _ in scored_with_penalty]
        
        logger.info(
            "Repeat penalty applied and candidates finalized",
            extra={
                "user_id": str(user.id),
                "session_id": str(recommendation_session.id),
                "candidate_count": len(candidates),
                "order_history_count": len(order_history),
                "days_threshold": 30
            }
        )
        
        session_feedback = session.exec(
            select(RecommendationFeedback).where(
                RecommendationFeedback.session_id == recommendation_session.id
            )
        ).all()
        
        items_map = {str(item.id): item for item in candidates}
        
        profile_adjustments = self.in_session_learning.get_temporary_profile_adjustments(
            user,
            session_feedback,
            items_map
        )
        
        # Load Bayesian profile (Phase 2 learning system)
        # Create profile on-demand if it doesn't exist
        bayesian_profile = self.bayesian_profile_service.get_or_create_profile(session, user)
        
        # INTELLIGENT EXPLORATION: Use Thompson Sampling for diversity BUT
        # blend with learned means to keep exploration centered on user preferences
        # This gives variety while respecting what user likes
        sampled_vector = bayesian_profile.sample_taste_preferences()
        mean_vector = bayesian_profile.mean_preferences.copy()
        
        # Blend: 70% learned preference + 30% exploration
        # This ensures recommendations vary but stay close to what user likes
        base_taste_vector = {
            axis: 0.7 * mean_vector.get(axis, 0.5) + 0.3 * sampled_vector.get(axis, 0.5)
            for axis in sampled_vector.keys()
        }
        
        logger.info(
            "Using controlled Thompson Sampling (70% learned + 30% exploration)",
            extra={
                "user_id": str(user.id),
                "session_id": str(recommendation_session.id),
                "profile_id": str(bayesian_profile.id),
                "mean_vector": {k: round(v, 3) for k, v in mean_vector.items()},
                "sampled_vector": {k: round(v, 3) for k, v in sampled_vector.items()},
                "final_vector": {k: round(v, 3) for k, v in base_taste_vector.items()}
            }
        )
        
        # Apply in-session adjustments on top of the base vector
        adjusted_taste_vector = base_taste_vector.copy()
        for axis, adjustment in profile_adjustments["taste_adjustments"].items():
            adjusted_taste_vector[axis] = max(0.0, min(1.0, adjusted_taste_vector[axis] + adjustment))
        
        pop = session.exec(select(PopulationStats)).first()
        pop_global = pop.item_popularity_global if pop else {}
        
        user_interaction_history = self.interaction_history_service.get_all_user_history(
            db_session=session,
            user_id=user.id
        )
        
        from services.features.features import clamp01
        base_scores: Dict[str, float] = {}
        for it in candidates:
            s = cosine_similarity(adjusted_taste_vector, it.features)
            
            # Apply cuisine affinity from Bayesian profile (persistent learning across sessions)
            for cuisine in it.cuisine:
                cuisine_pref = bayesian_profile.get_cuisine_preference(cuisine)
                # Convert 0-1 preference to stronger adjustment (Phase 2 Bayesian learning)
                cuisine_bonus = (cuisine_pref - 0.5) * 2.0 * settings.LAMBDA_CUISINE
                s += cuisine_bonus
            
            # Then apply in-session adjustments (temporary within session)
            for cuisine, adjustment in profile_adjustments["cuisine_adjustments"].items():
                if cuisine in it.cuisine:
                    s += adjustment * settings.LAMBDA_CUISINE
            
            popularity_score = pop_global.get(str(it.id), 0.0)
            s += settings.LAMBDA_POP * popularity_score
            
            if recommendation_session.user_experience_level == "new":
                s += popularity_score * 0.3
            
            for item, penalty in scored_with_penalty:
                if str(item.id) == str(it.id) and penalty < 0:
                    s += penalty
                    break
            
            novelty_bonus = self.interaction_history_service.calculate_novelty_bonus(
                user_interaction_history.get(it.id)
            )
            # Apply AGGRESSIVE penalty for disliked items (Bayesian learning
            # handles long-term preferences, this handles explicit rejections)
            # User explicitly rejected this - make it VERY unlikely to appear again
            if novelty_bonus < -0.5:
                s += novelty_bonus * 5.0  # Massive penalty for explicit dislikes/skips
            elif novelty_bonus < 0:
                s += novelty_bonus * 2.0  # Strong penalty for negative signals
            else:
                s += novelty_bonus * 0.2  # Scaled bonus for positive/neutral
            
            # Apply ingredient-level penalties for cross-restaurant learning
            # If user disliked items with mozzarella, penalize ALL mozzarella items
            ingredient_penalty = self._calculate_ingredient_penalty(user, it)
            if ingredient_penalty > 0:
                s -= ingredient_penalty
            
            base_scores[str(it.id)] = max(0.0, min(1.0, s))
        
        # CRITICAL: Sort candidates by base_scores to ensure highly-penalized items (disliked, skipped)
        # are at the end. This ensures meal composition uses the best-scored items first.
        candidates_sorted = sorted(
            candidates,
            key=lambda item: base_scores.get(str(item.id), 0.0),
            reverse=True
        )
        
        if recommendation_session.meal_intent == "full_meal":
            # Check if we need partial regeneration
            validation_state = recommendation_session.composition_validation_state.get(
                recommendation_session.active_composition_id or "", {}
            ) if recommendation_session.active_composition_id else {}
            
            # Determine which courses need regeneration
            accepted_items = {}
            courses_to_regenerate = []
            
            for course in ["appetizer", "main", "dessert"]:
                course_state = validation_state.get(course, {})
                status = course_state.get("status", "")
                
                if status == "accepted":
                    # Keep this item
                    from uuid import UUID as UUIDType
                    item_id = UUIDType(course_state.get("item_id"))
                    item = session.get(MenuItem, item_id)
                    if item:
                        accepted_items[course] = item
                else:
                    courses_to_regenerate.append(course)
            
            # If we have accepted items, do partial regeneration
            if accepted_items and courses_to_regenerate:
                composition_result = self.meal_composition.compose_partial_meal(
                    user,
                    candidates_sorted,
                    recommendation_session,
                    accepted_items=accepted_items,
                    courses_to_regenerate=courses_to_regenerate,
                    top_n=max(3, top_n // 3)
                )
            else:
                # Full composition generation
                composition_result = self.meal_composition.compose_full_meal(
                    user,
                    candidates_sorted,
                    recommendation_session,
                    top_n=max(3, top_n // 3)
                )
            
            if composition_result.compositions:
                results = []
                session_service = RecommendationSessionService()
                
                for idx, comp in enumerate(composition_result.compositions):
                    # Set first composition as active
                    if idx == 0:
                        session_service.set_active_composition(
                            db_session=session,
                            session_id=recommendation_session.id,
                            composition_id=comp.composition_id,
                            appetizer_id=comp.appetizer.id,
                            main_id=comp.main.id,
                            dessert_id=comp.dessert.id
                        )
                    
                    # Record all items in composition as shown for interaction history tracking
                    for item in [comp.appetizer, comp.main, comp.dessert]:
                        try:
                            self.interaction_history_service.record_item_shown(
                                db_session=session,
                                user_id=user.id,
                                item_id=item.id,
                                session_id=recommendation_session.id
                            )
                        except Exception as e:
                            logger.warning(
                                "Failed to record composition item view",
                                extra={
                                    "item_id": str(item.id),
                                    "error": str(e)
                                }
                            )
                    
                    explanation = self.explanation_enhancement.generate_multi_course_explanation(
                        comp,
                        user,
                        recommendation_session
                    )
                    
                    results.append({
                        "composition_id": comp.composition_id,
                        "items": [
                            self._format_item_response(session, comp.appetizer, user, recommendation_session, base_scores, order_history, user_interaction_history),
                            self._format_item_response(session, comp.main, user, recommendation_session, base_scores, order_history, user_interaction_history),
                            self._format_item_response(session, comp.dessert, user, recommendation_session, base_scores, order_history, user_interaction_history)
                        ],
                        "total_price": comp.total_price,
                        "estimated_duration_minutes": comp.estimated_duration_minutes,
                        "flavor_harmony_score": comp.flavor_harmony_score,
                        "explanation": explanation
                    })
                
                return {"items": results, "type": "composition"}
            
        # Apply MMR for diversity with configurable parameters
        diversity_weight = getattr(settings, 'RECOMMENDATION_DIVERSITY_WEIGHT', 0.3)
        use_mmr = getattr(settings, 'USE_MMR_DIVERSITY', True)
        
        # Create diversity constraints to prevent repetitive recommendations
        constraints = DiversityConstraints(
            max_items_per_cuisine=3,  # Max 3 items from same cuisine
            max_items_per_restaurant=None,  # Restaurant filtered upstream
            min_diversity_score=0.4  # Minimum acceptable diversity
        )
        
        if use_mmr and len(candidates) > top_n:
            logger.info(
                "Applying MMR diversity reranking",
                extra={
                    "candidate_count": len(candidates),
                    "top_n": top_n,
                    "diversity_weight": diversity_weight,
                    "user_id": str(user.id)
                }
            )
            
            # Use MMR to select diverse items
            # CRITICAL: Pass base_scores so MMR uses penalized scores, not fresh cosine similarity
            # This ensures dislike penalties, ingredient penalties, and novelty bonuses are preserved
            top_items = self.mmr_service.rerank_with_mmr(
                candidates=candidates,
                user_taste_vector=adjusted_taste_vector,
                k=top_n,
                diversity_weight=diversity_weight,
                constraints=constraints,
                base_scores=base_scores
            )
            
            final_diversity_score = self.mmr_service._compute_diversity_score(top_items)
            
            logger.info(
                "MMR diversity reranking completed",
                extra={
                    "final_count": len(top_items),
                    "diversity_score": round(final_diversity_score, 3),
                    "session_id": str(recommendation_session.id)
                }
            )
        else:
            # Fallback: deterministic ranking by base_scores (no randomization)
            logger.info(
                "Using deterministic ranking",
                extra={
                    "candidate_count": len(candidates),
                    "top_n": top_n,
                    "reason": "too_few_candidates" if len(candidates) <= top_n else "mmr_disabled"
                }
            )
            
            # Sort by base_scores for consistent, personalized recommendations
            sorted_items = sorted(
                candidates,
                key=lambda it: base_scores.get(str(it.id), 0.0),
                reverse=True
            )
            top_items = sorted_items[:top_n]
        
        logger.info(
            "Final recommendation set prepared",
            extra={
                "session_id": str(recommendation_session.id),
                "user_id": str(user.id),
                "item_count": len(top_items),
                "iteration": recommendation_session.iteration_count
            }
        )
        
        for item in top_items:
            try:
                self.interaction_history_service.record_item_shown(
                    db_session=session,
                    user_id=user.id,
                    item_id=item.id,
                    session_id=recommendation_session.id
                )
            except Exception as e:
                logger.warning(
                    "Failed to record item view",
                    extra={
                        "item_id": str(item.id),
                        "error": str(e)
                    }
                )
        
        results = []
        for idx, it in enumerate(top_items):
            results.append(self._format_item_response(
                session, it, user, recommendation_session, base_scores, 
                order_history, user_interaction_history
            ))
        
        return {"items": results, "type": "single"}
    
    def _format_item_response(
        self,
        db_session: Session,
        item: MenuItem,
        user: User,
        recommendation_session: RecommendationSession,
        base_scores: Dict[str, float],
        order_history: List[UserOrderHistory],
        user_interaction_history: Dict
    ) -> Dict[str, Any]:
        score = base_scores.get(str(item.id), 0.5)
        
        confidence, confidence_explanation = self.confidence_service.calculate_recommendation_confidence(
            db_session=db_session,
            user=user,
            item=item,
            recommendation_session=recommendation_session,
            base_score=score
        )
        
        novelty_indicator = self.confidence_service.get_novelty_indicator(
            user_interaction_history.get(item.id)
        )
        
        user_sorted = sorted(user.taste_vector.items(), key=lambda kv: kv[1], reverse=True)
        matched = [k for k, v in user_sorted if item.features.get(k, 0.0) > 0.5][:3]
        
        ranking_factors = {
            "taste_similarity": score,
            "course_match": 1.0 if item.course else 0.5
        }
        
        explanation = self.explanation_enhancement.generate_personalized_explanation(
            item,
            user,
            recommendation_session,
            ranking_factors,
            order_history,
            confidence
        )
        
        item_history = user_interaction_history.get(item.id)
        times_seen_before = item_history.times_shown if item_history else 0
        
        return {
            "item_id": str(item.id),
            "name": item.name,
            "description": item.description,
            "course": item.course,
            "price": item.price,
            "score": round(score, 3),
            "confidence": round(confidence, 2),
            "confidence_explanation": confidence_explanation,
            "novelty_indicator": novelty_indicator,
            "times_seen_before": times_seen_before,
            "explanation": explanation,
            "matched_axes": matched,
            "cuisine": item.cuisine,
            "dietary_tags": item.dietary_tags,
            "features": item.features,
            "safety_confidence": 1.0
        }
    
    def _calculate_ingredient_penalty(self, user: User, item: MenuItem) -> float:
        if not hasattr(user, "ingredient_penalties") or not user.ingredient_penalties:
            return 0.0
        
        if not item.ingredients:
            return 0.0
        
        total_penalty = 0.0
        matching_ingredients = []
        
        # Check item's ingredients against user's learned ingredient penalties
        for ingredient in item.ingredients[:10]:  # Check top 10 ingredients
            ingredient_lower = ingredient.lower().strip()
            if ingredient_lower in user.ingredient_penalties:
                penalty = user.ingredient_penalties[ingredient_lower]
                total_penalty += penalty
                matching_ingredients.append(f"{ingredient_lower}({penalty:.2f})")
        
        if total_penalty > 0:
            logger.debug(
                "Applied ingredient penalty",
                extra={
                    "user_id": str(user.id),
                    "item_id": str(item.id),
                    "item_name": item.name,
                    "total_penalty": round(total_penalty, 3),
                    "matching_ingredients": matching_ingredients
                }
            )
        
        # Scale penalty: each disliked ingredient contributes, but cap at 0.5 total
        return min(0.5, total_penalty * 0.1)

