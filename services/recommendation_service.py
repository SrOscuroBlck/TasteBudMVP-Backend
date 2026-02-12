from __future__ import annotations
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlmodel import Session, select
from models import User, MenuItem, PopulationStats, RecommendationSession, RecommendationFeedback, UserOrderHistory
from .features import cosine_similarity, has_allergen, violates_diet
from .gpt_helper import generate_rationale
from .retrieval_service import RetrievalService
from .reranking_service import RerankingService, RecommendationContext
from .ml_reranking_service import MLRerankingService
from .explanation_service import ExplanationService
from .context_enhancement_service import ContextEnhancementService
from .in_session_learning_service import InSessionLearningService
from .meal_composition_service import MealCompositionService
from .explanation_enhancement_service import ExplanationEnhancementService
from .interaction_history_service import InteractionHistoryService
from .confidence_service import ConfidenceService
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
                budget=budget
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
        
        logger.info(
            "Starting safety filtering",
            extra={
                "user_id": str(user.id),
                "total_items": len(all_items),
                "permanently_excluded_count": len(user.permanently_excluded_items),
                "permanently_excluded_items": user.permanently_excluded_items
            }
        )
        
        for it in all_items:
            if user_all.intersection(set(map(str.lower, it.allergens))):
                continue
            if has_allergen(user.allergies, it.ingredients, explicit_allergens=it.allergens):
                continue
            if violates_diet(user.dietary_rules, it.dietary_tags):
                continue
            if recommendation_session.budget and it.price and it.price > recommendation_session.budget * 1.2:
                continue
            
            item_id_str = str(it.id)
            if item_id_str in recommendation_session.excluded_items:
                continue
            
            if item_id_str in user.permanently_excluded_items:
                logger.debug(
                    "Item filtered - permanently excluded",
                    extra={"item_id": item_id_str, "item_name": it.name}
                )
                continue
            
            safe.append(it)
        
        if not safe:
            return {"items": [], "warnings": ["no_safe_items"]}
        
        # Don't apply strict time filtering for full_meal (user wants to see everything)
        apply_strict_time_filter = recommendation_session.meal_intent != "full_meal"
        
        time_filtered = self.context_service.apply_hard_time_filters(
            safe,
            recommendation_session.detected_hour,
            strict=apply_strict_time_filter
        )
        
        intent_filtered = self.context_service.apply_meal_intent_filters(
            time_filtered,
            recommendation_session.meal_intent,
            recommendation_session.hunger_level
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
        
        adjusted_taste_vector = user.taste_vector.copy()
        for axis, adjustment in profile_adjustments["taste_adjustments"].items():
            adjusted_taste_vector[axis] = max(0.0, min(1.0, adjusted_taste_vector[axis] + adjustment))
        
        pop = session.exec(select(PopulationStats)).first()
        pop_global = pop.item_popularity_global if pop else {}
        
        user_interaction_history = self.interaction_history_service.get_all_user_history(
            db_session=session,
            user_id=user.id
        )
        
        from .features import clamp01
        base_scores: Dict[str, float] = {}
        for it in candidates:
            s = cosine_similarity(adjusted_taste_vector, it.features)
            
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
            s += novelty_bonus * 0.2
            
            base_scores[str(it.id)] = max(0.0, min(1.0, s))
        
        if recommendation_session.meal_intent == "full_meal":
            composition_result = self.meal_composition.compose_full_meal(
                user,
                candidates,
                recommendation_session,
                top_n=max(3, top_n // 3)
            )
            
            if composition_result.compositions:
                results = []
                for comp in composition_result.compositions:
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
            
        sorted_items = sorted(candidates, key=lambda it: base_scores.get(str(it.id), 0.0), reverse=True)
        top_items = sorted_items[:top_n]
        
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

