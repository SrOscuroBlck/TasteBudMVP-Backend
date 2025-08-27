from __future__ import annotations
from typing import Dict, Any, List, Tuple
from sqlmodel import Session, select
from models import User, MenuItem, PopulationStats
from .features import cosine_similarity, has_allergen, violates_diet
from .gpt_helper import generate_rationale
from config.settings import settings
import math
from datetime import datetime


def time_decay_score(ts: datetime, half_life_days: int) -> float:
    if not ts:
        return 1.0
    days = (datetime.utcnow() - ts).days
    return 0.5 ** (days / max(1, half_life_days))


class RecommendationService:
    def recommend(self, session: Session, user: User, restaurant_id: str = None, top_n: int = 10, budget: float = None, time_of_day: str = None) -> Dict[str, Any]:
        # 1) candidates
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
