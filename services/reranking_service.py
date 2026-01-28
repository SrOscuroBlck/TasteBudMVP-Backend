from typing import List, Dict, Any, Optional
from datetime import datetime
import math

from models import MenuItem, User, PopulationStats
from services.features import cosine_similarity
from config.settings import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class RecommendationContext:
    def __init__(
        self,
        time_of_day: Optional[str] = None,
        budget: Optional[float] = None,
        mood: Optional[str] = None,
        occasion: Optional[str] = None
    ):
        self.time_of_day = time_of_day
        self.budget = budget
        self.mood = mood
        self.occasion = occasion


class RankedItem:
    def __init__(
        self,
        item: MenuItem,
        base_score: float,
        contextual_score: float,
        confidence: float,
        ranking_factors: Dict[str, float]
    ):
        self.item = item
        self.base_score = base_score
        self.contextual_score = contextual_score
        self.confidence = confidence
        self.ranking_factors = ranking_factors
    
    @property
    def final_score(self) -> float:
        return self.contextual_score


class RerankingService:
    def __init__(self, population_stats: Optional[PopulationStats] = None):
        self.population_stats = population_stats
        
    def rerank(
        self,
        candidates: List[MenuItem],
        user: User,
        context: RecommendationContext,
        top_n: int = 10
    ) -> List[RankedItem]:
        if not candidates:
            return []
        
        base_scored = self._calculate_base_scores(candidates, user)
        
        contextual_scored = self._apply_contextual_adjustments(
            base_scored, context
        )
        
        diversified = self._apply_mmr_diversification(
            contextual_scored, top_n
        )
        
        return diversified[:top_n]
    
    def _calculate_base_scores(
        self,
        candidates: List[MenuItem],
        user: User
    ) -> List[RankedItem]:
        ranked_items = []
        
        for item in candidates:
            if not item.features:
                continue
            
            taste_sim = cosine_similarity(user.taste_vector, item.features)
            
            cuisine_bonus = self._calculate_cuisine_affinity(item, user)
            
            popularity_bonus = self._calculate_popularity(item)
            
            ingredient_bonus = self._calculate_ingredient_preferences(item, user)
            
            confidence = self._calculate_confidence(item)
            
            provenance_penalty = 0.0
            if item.provenance.get("source") == "gpt_inferred":
                conf = item.inference_confidence or 0.5
                provenance_penalty = settings.GPT_CONFIDENCE_DISCOUNT * (1.0 - conf)
            
            base_score = (
                taste_sim +
                settings.LAMBDA_CUISINE * cuisine_bonus +
                settings.LAMBDA_POP * popularity_bonus +
                ingredient_bonus -
                provenance_penalty
            )
            base_score = max(0.0, min(1.0, base_score))
            
            ranking_factors = {
                "taste_similarity": taste_sim,
                "cuisine_affinity": cuisine_bonus,
                "popularity": popularity_bonus,
                "ingredient_preferences": ingredient_bonus,
                "provenance_penalty": provenance_penalty
            }
            
            ranked_items.append(RankedItem(
                item=item,
                base_score=base_score,
                contextual_score=base_score,
                confidence=confidence,
                ranking_factors=ranking_factors
            ))
        
        return ranked_items
    
    def _apply_contextual_adjustments(
        self,
        items: List[RankedItem],
        context: RecommendationContext
    ) -> List[RankedItem]:
        for ranked_item in items:
            item = ranked_item.item
            adjustments = 0.0
            
            if context.time_of_day:
                time_adj = self._time_of_day_adjustment(item, context.time_of_day)
                adjustments += time_adj
                ranked_item.ranking_factors["time_of_day_adjustment"] = time_adj
            
            if context.budget and item.price:
                budget_adj = self._budget_adjustment(item.price, context.budget)
                adjustments += budget_adj
                ranked_item.ranking_factors["budget_adjustment"] = budget_adj
            
            if context.mood:
                mood_adj = self._mood_adjustment(item, context.mood)
                adjustments += mood_adj
                ranked_item.ranking_factors["mood_adjustment"] = mood_adj
            
            if context.occasion:
                occasion_adj = self._occasion_adjustment(item, context.occasion)
                adjustments += occasion_adj
                ranked_item.ranking_factors["occasion_adjustment"] = occasion_adj
            
            ranked_item.contextual_score = max(0.0, min(1.0, ranked_item.base_score + adjustments))
        
        items.sort(key=lambda x: x.contextual_score, reverse=True)
        return items
    
    def _apply_mmr_diversification(
        self,
        items: List[RankedItem],
        top_n: int
    ) -> List[RankedItem]:
        if len(items) <= top_n:
            return items
        
        selected: List[RankedItem] = []
        remaining = items.copy()
        alpha = settings.MMR_ALPHA
        
        while len(selected) < top_n and remaining:
            best_item = None
            best_mmr_score = -math.inf
            best_idx = -1
            
            for idx, candidate in enumerate(remaining):
                relevance = candidate.contextual_score
                
                diversity_penalty = 0.0
                if selected:
                    similarities = [
                        cosine_similarity(
                            candidate.item.features,
                            s.item.features
                        )
                        for s in selected
                        if s.item.features and candidate.item.features
                    ]
                    if similarities:
                        max_similarity = max(similarities)
                        diversity_penalty = (1 - alpha) * max_similarity
                
                mmr_score = alpha * relevance - diversity_penalty
                
                if mmr_score > best_mmr_score:
                    best_mmr_score = mmr_score
                    best_item = candidate
                    best_idx = idx
            
            if best_item is None:
                break
            
            selected.append(best_item)
            remaining.pop(best_idx)
        
        return selected
    
    def _calculate_cuisine_affinity(
        self,
        item: MenuItem,
        user: User
    ) -> float:
        if not item.cuisine:
            return 0.0
        
        affinities = [
            user.cuisine_affinity.get(cuisine, 0.0)
            for cuisine in item.cuisine
        ]
        return max(affinities) if affinities else 0.0
    
    def _calculate_popularity(self, item: MenuItem) -> float:
        if not self.population_stats:
            return 0.0
        
        pop_global = self.population_stats.item_popularity_global or {}
        pop_rest = self.population_stats.item_popularity_by_restaurant or {}
        
        global_score = pop_global.get(str(item.id), 0.0)
        restaurant_score = pop_rest.get(str(item.restaurant_id), 0.0)
        
        return min(1.0, global_score + restaurant_score)
    
    def _calculate_ingredient_preferences(
        self,
        item: MenuItem,
        user: User
    ) -> float:
        bonus = 0.0
        
        item_ingredients_lower = set(map(str.lower, item.ingredients))
        
        disliked_lower = set(map(str.lower, user.disliked_ingredients))
        if item_ingredients_lower.intersection(disliked_lower):
            bonus -= 0.1
        
        liked_lower = set(map(str.lower, user.liked_ingredients))
        if item_ingredients_lower.intersection(liked_lower):
            bonus += 0.05
        
        return bonus
    
    def _calculate_confidence(self, item: MenuItem) -> float:
        confidence = 0.5
        
        if item.features:
            confidence += 0.2
        
        if item.ingredients:
            confidence += 0.1
        
        if item.provenance.get("source") == "ingested":
            confidence += 0.2
        else:
            conf = item.inference_confidence or 0.5
            confidence += 0.2 * conf
        
        return min(1.0, confidence)
    
    def _time_of_day_adjustment(self, item: MenuItem, time_of_day: str) -> float:
        breakfast_courses = ["breakfast", "brunch"]
        lunch_courses = ["lunch", "appetizer", "salad", "sandwich"]
        dinner_courses = ["dinner", "entree", "main"]
        
        if time_of_day == "morning":
            if item.course and item.course.lower() in breakfast_courses:
                return 0.15
            elif item.course and item.course.lower() in dinner_courses:
                return -0.10
        
        elif time_of_day == "afternoon":
            if item.course and item.course.lower() in lunch_courses:
                return 0.10
        
        elif time_of_day == "evening":
            if item.course and item.course.lower() in dinner_courses:
                return 0.15
            elif item.course and item.course.lower() in breakfast_courses:
                return -0.10
        
        return 0.0
    
    def _budget_adjustment(self, price: float, budget: float) -> float:
        if price > budget:
            excess = (price - budget) / budget
            return -0.2 * min(1.0, excess)
        
        if price < budget * 0.5:
            return 0.05
        
        return 0.0
    
    def _mood_adjustment(self, item: MenuItem, mood: str) -> float:
        if mood == "adventurous":
            if item.spice_level and item.spice_level >= 3:
                return 0.10
            
            if item.cuisine and any(c.lower() in ["thai", "indian", "ethiopian", "korean"] for c in item.cuisine):
                return 0.08
        
        elif mood == "comfort":
            comfort_methods = ["baked", "fried", "grilled", "roasted"]
            if item.cooking_method and item.cooking_method.lower() in comfort_methods:
                return 0.10
        
        elif mood == "healthy":
            healthy_tags = ["vegan", "vegetarian", "gluten-free", "low-calorie"]
            if any(tag.lower() in healthy_tags for tag in item.dietary_tags):
                return 0.10
        
        return 0.0
    
    def _occasion_adjustment(self, item: MenuItem, occasion: str) -> float:
        if occasion == "date_night":
            if item.price and item.price > 20:
                return 0.10
        
        elif occasion == "quick_bite":
            if item.course and item.course.lower() in ["appetizer", "sandwich", "salad"]:
                return 0.10
        
        elif occasion == "celebration":
            if item.price and item.price > 25:
                return 0.12
        
        return 0.0
