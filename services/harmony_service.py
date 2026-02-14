from typing import List, Dict, Optional
from models import MenuItem
from models.user import TASTE_AXES
from utils.culinary_rules import COMPLEMENTARY_PAIRINGS, REPETITION_PENALTY, IDEAL_RICHNESS_PROGRESSION
from utils.logger import setup_logger

logger = setup_logger(__name__)


class HarmonyService:
    
    def calculate_meal_harmony(
        self,
        appetizer: MenuItem,
        main: MenuItem,
        dessert: Optional[MenuItem] = None
    ) -> Dict[str, float]:
        if not appetizer or not main:
            raise ValueError("appetizer and main are required for harmony calculation")
        
        contrast_score = self._taste_contrast_score(appetizer, main)
        
        if dessert:
            contrast_score += self._taste_contrast_score(main, dessert)
            contrast_score /= 2.0
        
        courses = [appetizer, main]
        if dessert:
            courses.append(dessert)
        
        arc_score = self._intensity_arc_score(courses)
        
        diversity_score = self._ingredient_diversity_score(courses)
        
        total_harmony = 0.4 * contrast_score + 0.3 * arc_score + 0.3 * diversity_score
        
        result = {
            "total_harmony": round(total_harmony, 3),
            "taste_contrast": round(contrast_score, 3),
            "intensity_arc": round(arc_score, 3),
            "ingredient_diversity": round(diversity_score, 3)
        }
        
        logger.info(
            "Harmony calculated for meal",
            extra={
                "appetizer": appetizer.name,
                "main": main.name,
                "dessert": dessert.name if dessert else None,
                "harmony_scores": result
            }
        )
        
        return result
    
    def _taste_contrast_score(self, course1: MenuItem, course2: MenuItem) -> float:
        if not course1.features or not course2.features:
            return 0.0
        
        score = 0.0
        
        dominant1 = self._get_dominant_taste(course1.features)
        dominant2 = self._get_dominant_taste(course2.features)
        
        pairing_key = (dominant1, dominant2)
        if pairing_key in COMPLEMENTARY_PAIRINGS:
            score += COMPLEMENTARY_PAIRINGS[pairing_key]
        
        for taste in TASTE_AXES:
            value1 = course1.features.get(taste, 0.0)
            value2 = course2.features.get(taste, 0.0)
            
            if value1 > 0.6 and value2 > 0.6:
                pairing_key = (taste, taste)
                if pairing_key in COMPLEMENTARY_PAIRINGS:
                    score += COMPLEMENTARY_PAIRINGS[pairing_key]
        
        if dominant1 == dominant2 and dominant1 not in ["umami"]:
            score += REPETITION_PENALTY
        
        return max(-1.0, min(1.0, score))
    
    def _get_dominant_taste(self, features: Dict[str, float]) -> str:
        if not features:
            return "none"
        
        max_taste = "sweet"
        max_value = 0.0
        
        for taste in TASTE_AXES:
            value = features.get(taste, 0.0)
            if value > max_value:
                max_value = value
                max_taste = taste
        
        return max_taste
    
    def _intensity_arc_score(self, courses: List[MenuItem]) -> float:
        if not courses or len(courses) < 2:
            return 0.0
        
        richness_values = []
        for course in courses:
            if course.richness is not None:
                richness_values.append(course.richness)
            else:
                estimated_richness = self._estimate_richness_from_features(course)
                richness_values.append(estimated_richness)
        
        if len(richness_values) < 2:
            return 0.0
        
        score = 0.0
        
        if len(richness_values) == 2:
            appetizer_rich = richness_values[0]
            main_rich = richness_values[1]
            
            if appetizer_rich < main_rich:
                score += 0.4 * (main_rich - appetizer_rich)
            else:
                score -= 0.3 * (appetizer_rich - main_rich)
        
        elif len(richness_values) == 3:
            appetizer_rich = richness_values[0]
            main_rich = richness_values[1]
            dessert_rich = richness_values[2]
            
            if appetizer_rich < main_rich:
                score += 0.4 * (main_rich - appetizer_rich)
            else:
                score -= 0.3 * (appetizer_rich - main_rich)
            
            if main_rich > dessert_rich:
                score += 0.2
            
            if appetizer_rich > 0.7:
                score -= 0.3
        
        return max(-1.0, min(1.0, score))
    
    def _estimate_richness_from_features(self, item: MenuItem) -> float:
        if not item.features:
            return 0.5
        
        fatty = item.features.get("fatty", 0.0)
        umami = item.features.get("umami", 0.0)
        sweet = item.features.get("sweet", 0.0)
        
        estimated = 0.5 * fatty + 0.3 * umami + 0.2 * sweet
        
        return max(0.0, min(1.0, estimated))
    
    def _ingredient_diversity_score(self, courses: List[MenuItem]) -> float:
        if not courses:
            return 0.0
        
        all_ingredients = []
        for course in courses:
            if course.ingredients:
                primary_ingredients = course.ingredients[:3]
                all_ingredients.extend([ing.lower() for ing in primary_ingredients])
        
        if not all_ingredients:
            return 0.0
        
        unique_count = len(set(all_ingredients))
        total_count = len(all_ingredients)
        
        diversity_ratio = unique_count / max(1, total_count)
        
        if diversity_ratio < 0.7:
            return -0.3 * (0.7 - diversity_ratio)
        
        return 0.1 * (diversity_ratio - 0.7)
    
    def calculate_pairwise_harmony(
        self,
        item1: MenuItem,
        item2: MenuItem
    ) -> float:
        if not item1 or not item2:
            raise ValueError("Both items required for pairwise harmony")
        
        contrast = self._taste_contrast_score(item1, item2)
        
        diversity = self._ingredient_diversity_score([item1, item2])
        
        harmony = 0.6 * contrast + 0.4 * diversity
        
        return round(harmony, 3)
