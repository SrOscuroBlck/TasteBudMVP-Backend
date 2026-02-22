from typing import List, Dict, Any, Optional
from datetime import datetime
import math

from models import MenuItem, User, PopulationStats, BayesianTasteProfile
from services.features.features import cosine_similarity
from config.settings import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class RecommendationContext:
    def __init__(
        self,
        time_of_day: Optional[str] = None,
        budget: Optional[float] = None,
        mood: Optional[str] = None,
        occasion: Optional[str] = None,
        course_preference: Optional[str] = None
    ):
        self.time_of_day = time_of_day or self._auto_detect_time_of_day()
        self.budget = budget
        self.mood = mood
        self.occasion = occasion
        self.course_preference = course_preference
        self.current_hour = datetime.now().hour
        self.day_of_week = datetime.now().weekday()
    
    def _auto_detect_time_of_day(self) -> str:
        """Auto-detect time of day based on current hour."""
        hour = datetime.now().hour
        
        if 6 <= hour < 11:
            return "morning"
        elif 11 <= hour < 15:
            return "afternoon"
        elif 15 <= hour < 18:
            return "late_afternoon"
        elif 18 <= hour < 22:
            return "evening"
        else:
            return "night"


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
        self.use_bayesian_profiles = True
        
    def rerank(
        self,
        candidates: List[MenuItem],
        user: User,
        context: RecommendationContext,
        top_n: int = 10,
        bayesian_profile: Optional[BayesianTasteProfile] = None
    ) -> List[RankedItem]:
        if not candidates:
            return []
        
        logger.info(
            "Starting reranking",
            extra={
                "candidate_count": len(candidates),
                "top_n": top_n,
                "use_bayesian": self.use_bayesian_profiles and bayesian_profile is not None
            }
        )
        
        base_scored = self._calculate_base_scores(candidates, user, bayesian_profile)
        logger.info(
            "After base scoring",
            extra={"item_count": len(base_scored)}
        )
        
        contextual_scored = self._apply_contextual_adjustments(
            base_scored, context
        )
        logger.info(
            "After contextual adjustments",
            extra={"item_count": len(contextual_scored)}
        )
        
        diversified = self._apply_mmr_diversification(
            contextual_scored, top_n
        )
        logger.info(
            "After MMR diversification",
            extra={"item_count": len(diversified)}
        )
        
        return diversified[:top_n]
    
    def _calculate_base_scores(
        self,
        candidates: List[MenuItem],
        user: User,
        bayesian_profile: Optional[BayesianTasteProfile] = None
    ) -> List[RankedItem]:
        ranked_items = []
        
        use_bayesian = self.use_bayesian_profiles and bayesian_profile is not None
        
        sampled_tastes = None
        if use_bayesian:
            sampled_tastes = bayesian_profile.sample_taste_preferences()
        
        logger.info(
            "Starting base score calculation",
            extra={
                "candidate_count": len(candidates),
                "user_taste_vector": user.taste_vector if not use_bayesian else sampled_tastes,
                "using_bayesian": use_bayesian
            }
        )
        
        for item in candidates:
            if not item.features:
                logger.warning(
                    "Skipping item without features",
                    extra={
                        "item_id": str(item.id),
                        "item_name": item.name,
                        "features": item.features
                    }
                )
                continue
            
            if use_bayesian and sampled_tastes:
                taste_sim = cosine_similarity(sampled_tastes, item.features)
                cuisine_bonus = self._calculate_cuisine_affinity_bayesian(item, bayesian_profile)
            else:
                taste_sim = cosine_similarity(user.taste_vector, item.features)
                cuisine_bonus = self._calculate_cuisine_affinity(item, user)
            
            popularity_bonus = self._calculate_popularity(item)
            
            ingredient_bonus = self._calculate_ingredient_preferences(item, user)
            
            exploration_bonus = self._calculate_exploration_bonus(item, user)
            
            confidence = self._calculate_confidence(item)
            
            provenance_penalty = 0.0
            if item.provenance.get("source") == "gpt_inferred":
                conf = item.inference_confidence or 0.5
                provenance_penalty = settings.GPT_CONFIDENCE_DISCOUNT * (1.0 - conf)
            
            base_score = (
                taste_sim +
                settings.LAMBDA_CUISINE * cuisine_bonus +
                settings.LAMBDA_POP * popularity_bonus +
                ingredient_bonus +
                exploration_bonus -
                provenance_penalty
            )
            base_score = max(0.0, min(1.0, base_score))
            
            ranking_factors = {
                "taste_similarity": taste_sim,
                "cuisine_affinity": cuisine_bonus,
                "popularity": popularity_bonus,
                "ingredient_preferences": ingredient_bonus,
                "exploration_bonus": exploration_bonus,
                "provenance_penalty": provenance_penalty
            }
            
            ranked_items.append(RankedItem(
                item=item,
                base_score=base_score,
                contextual_score=base_score,
                confidence=confidence,
                ranking_factors=ranking_factors
            ))
        
        logger.info(
            "Base score calculation complete",
            extra={
                "ranked_item_count": len(ranked_items),
                "top_3_scores": [round(ri.base_score, 3) for ri in sorted(ranked_items, key=lambda x: x.base_score, reverse=True)[:3]]
            }
        )
        
        return ranked_items
    
    def _apply_contextual_adjustments(
        self,
        items: List[RankedItem],
        context: RecommendationContext
    ) -> List[RankedItem]:
        for ranked_item in items:
            item = ranked_item.item
            adjustments = 0.0
            
            course_adj = self._course_adjustment(item, context.course_preference)
            adjustments += course_adj
            ranked_item.ranking_factors["course_adjustment"] = course_adj
            
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
        
        if not user.cuisine_affinity:
            return 0.0
        
        affinities = [
            user.cuisine_affinity.get(cuisine, 0.0)
            for cuisine in item.cuisine
        ]
        return max(affinities) if affinities else 0.0
    
    def _calculate_cuisine_affinity_bayesian(
        self,
        item: MenuItem,
        profile: BayesianTasteProfile
    ) -> float:
        if not item.cuisine:
            return 0.0
        
        if not profile.cuisine_means:
            return 0.0
        
        affinities = [
            profile.cuisine_means.get(cuisine, 0.5)
            for cuisine in item.cuisine
        ]
        return max(affinities) if affinities else 0.5
    
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
    
    def _calculate_exploration_bonus(self, item: MenuItem, user: User) -> float:
        if not user.taste_uncertainty or not item.features:
            return 0.0
        
        exploration_score = 0.0
        
        for axis, feature_value in item.features.items():
            uncertainty = user.taste_uncertainty.get(axis, 0.5)
            
            exploration_score += uncertainty * abs(feature_value)
        
        normalized_score = exploration_score / max(1.0, len(item.features))
        
        return settings.EXPLORATION_COEFFICIENT * normalized_score
    
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
    
    def _course_adjustment(self, item: MenuItem, course_preference: Optional[str]) -> float:
        if not item.course:
            return 0.0
        
        item_course = item.course.lower()
        
        if course_preference:
            preference = course_preference.lower()
            
            if preference in ["beverage", "drink", "drinks", "beverages"]:
                if item_course == "beverage":
                    return 0.4
                else:
                    return -0.3
            
            elif preference in ["main", "entree", "main course", "mains"]:
                if item_course == "main":
                    return 0.3
                elif item_course in ["beverage", "condiment", "pantry"]:
                    return -0.4
                else:
                    return 0.0
            
            elif preference in ["appetizer", "appetizers", "starter", "starters"]:
                if item_course in ["appetizer", "starter"]:
                    return 0.3
                elif item_course in ["beverage", "condiment", "pantry"]:
                    return -0.4
                else:
                    return -0.1
            
            elif preference in ["dessert", "desserts", "sweet", "sweets"]:
                if item_course == "dessert":
                    return 0.3
                elif item_course in ["beverage", "condiment", "pantry"]:
                    return -0.4
                else:
                    return -0.2
            
            elif preference in ["side", "sides"]:
                if item_course == "side":
                    return 0.3
                else:
                    return -0.2
        
        else:
            if item_course == "beverage":
                return -0.5
            
            elif item_course in ["condiment", "pantry"]:
                return -0.6
            
            elif item_course in ["main", "appetizer", "starter"]:
                return 0.1
            
            elif item_course == "dessert":
                return 0.0
        
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
