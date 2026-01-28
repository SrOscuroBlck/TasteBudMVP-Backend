from __future__ import annotations
from typing import Dict, Any, List, Optional
from sqlmodel import Session, select
from models import User, MenuItem, PopulationStats
from .features import cosine_similarity, has_allergen, violates_diet
from .gpt_helper import generate_rationale
from .retrieval_service import RetrievalService
from .reranking_service import RerankingService, RecommendationContext
from .explanation_service import ExplanationService
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
    def __init__(self, use_new_pipeline: bool = True):
        self.use_new_pipeline = use_new_pipeline
        self.retrieval_service = RetrievalService() if use_new_pipeline else None
        self.reranking_service = None
        self.explanation_service = ExplanationService() if use_new_pipeline else None
    
    def recommend(
        self,
        session: Session,
        user: User,
        restaurant_id: Optional[str] = None,
        top_n: int = 10,
        budget: Optional[float] = None,
        time_of_day: Optional[str] = None,
        mood: Optional[str] = None,
        occasion: Optional[str] = None
    ) -> Dict[str, Any]:
        if self.use_new_pipeline:
            return self._recommend_new_pipeline(
                session, user, restaurant_id, top_n,
                budget, time_of_day, mood, occasion
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
        occasion: Optional[str]
    ) -> Dict[str, Any]:
        logger.info(
            "Generating recommendations with new pipeline",
            extra={
                "user_id": str(user.id),
                "restaurant_id": restaurant_id,
                "top_n": top_n
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
        if not self.reranking_service:
            self.reranking_service = RerankingService(population_stats=pop_stats)
        
        context = RecommendationContext(
            time_of_day=time_of_day,
            budget=budget,
            mood=mood,
            occasion=occasion
        )
        
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
