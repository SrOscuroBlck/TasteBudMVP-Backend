from __future__ import annotations
from typing import List, Dict, Optional
from dataclasses import dataclass
from uuid import uuid4

from models import MenuItem, User, RecommendationSession
from services.features import cosine_similarity
from utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class CourseCombination:
    composition_id: str
    appetizer: MenuItem
    main: MenuItem
    dessert: MenuItem
    total_price: float
    estimated_duration_minutes: int
    flavor_harmony_score: float
    overall_score: float


@dataclass
class FullMealComposition:
    compositions: List[CourseCombination]
    message: Optional[str] = None


class MealCompositionService:
    def compose_full_meal(
        self,
        user: User,
        candidates: List[MenuItem],
        session_context: RecommendationSession,
        top_n: int = 3
    ) -> FullMealComposition:
        appetizers = [
            item for item in candidates
            if item.course and any(c in item.course.lower() for c in ["appetizer", "starter", "salad", "soup"])
        ]
        
        mains = [
            item for item in candidates
            if item.course and any(c in item.course.lower() for c in ["main", "entree", "dinner"])
        ]
        
        desserts = [
            item for item in candidates
            if item.course and "dessert" in item.course.lower()
        ]
        
        if not appetizers or not mains or not desserts:
            logger.warning(
                "Insufficient courses for full meal",
                extra={
                    "appetizers": len(appetizers),
                    "mains": len(mains),
                    "desserts": len(desserts)
                }
            )
            return FullMealComposition(
                compositions=[],
                message="Not enough course variety available for full meal"
            )
        
        combinations = self.find_compatible_courses(
            appetizers[:10],
            mains[:10],
            desserts[:10],
            session_context.budget
        )
        
        if not combinations:
            return FullMealComposition(
                compositions=[],
                message="Could not find compatible course combinations"
            )
        
        combinations.sort(key=lambda x: x.overall_score, reverse=True)
        
        logger.info(
            "Meal compositions created",
            extra={
                "session_id": str(session_context.id),
                "combinations": len(combinations),
                "returning": min(top_n, len(combinations))
            }
        )
        
        return FullMealComposition(
            compositions=combinations[:top_n]
        )
    
    def find_compatible_courses(
        self,
        appetizers: List[MenuItem],
        mains: List[MenuItem],
        desserts: List[MenuItem],
        max_price: Optional[float]
    ) -> List[CourseCombination]:
        combinations = []
        
        for appetizer in appetizers[:5]:
            for main in mains[:5]:
                for dessert in desserts[:3]:
                    total_price = (
                        (appetizer.price or 0) +
                        (main.price or 0) +
                        (dessert.price or 0)
                    )
                    
                    if max_price and total_price > max_price * 1.15:
                        continue
                    
                    harmony_score = self.calculate_flavor_harmony([appetizer, main, dessert])
                    duration = self.estimate_meal_duration([appetizer, main, dessert])
                    
                    cooking_methods = {
                        appetizer.cooking_method,
                        main.cooking_method,
                        dessert.cooking_method
                    }
                    variety_bonus = len([m for m in cooking_methods if m]) / 3.0
                    
                    overall_score = harmony_score * 0.7 + variety_bonus * 0.3
                    
                    if max_price:
                        price_ratio = total_price / max_price
                        if price_ratio > 1.0:
                            overall_score *= 0.9
                    
                    combination = CourseCombination(
                        composition_id=str(uuid4()),
                        appetizer=appetizer,
                        main=main,
                        dessert=dessert,
                        total_price=total_price,
                        estimated_duration_minutes=duration,
                        flavor_harmony_score=harmony_score,
                        overall_score=overall_score
                    )
                    
                    combinations.append(combination)
        
        return combinations
    
    def calculate_flavor_harmony(self, courses: List[MenuItem]) -> float:
        if len(courses) < 2:
            return 1.0
        
        harmony_scores = []
        
        for i in range(len(courses) - 1):
            similarity = cosine_similarity(
                courses[i].features,
                courses[i + 1].features
            )
            
            ideal_similarity = 0.4
            distance_from_ideal = abs(similarity - ideal_similarity)
            harmony = 1.0 - (distance_from_ideal * 0.5)
            
            harmony_scores.append(max(0.0, min(1.0, harmony)))
        
        cuisines = []
        for course in courses:
            cuisines.extend(course.cuisine)
        
        unique_cuisines = len(set(cuisines))
        if unique_cuisines <= 2:
            cuisine_harmony = 1.0
        elif unique_cuisines == 3:
            cuisine_harmony = 0.7
        else:
            cuisine_harmony = 0.5
        
        spice_levels = [
            course.spice_level for course in courses
            if course.spice_level is not None
        ]
        if len(spice_levels) > 1:
            spice_variance = max(spice_levels) - min(spice_levels)
            spice_harmony = 1.0 - (spice_variance / 10.0)
        else:
            spice_harmony = 1.0
        
        final_harmony = (
            sum(harmony_scores) / len(harmony_scores) * 0.5 +
            cuisine_harmony * 0.3 +
            spice_harmony * 0.2
        )
        
        return max(0.0, min(1.0, final_harmony))
    
    def estimate_meal_duration(self, courses: List[MenuItem]) -> int:
        base_duration = 60
        per_course = 15
        
        total_duration = base_duration + (len(courses) * per_course)
        
        return total_duration
