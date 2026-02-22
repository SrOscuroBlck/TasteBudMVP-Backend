"""
Confidence Scoring Service

Calculates confidence scores for recommendations based on:
- User profile certainty (how well we know their tastes)
- Item feature completeness
- Number of similar items user has rated
- Context match strength
"""

from typing import Dict, Optional
from uuid import UUID
from sqlmodel import Session, select
from models import User, MenuItem
from models.session import RecommendationSession
from models.feedback import Rating
from models.interaction_history import UserItemInteractionHistory
from utils.logger import setup_logger

logger = setup_logger(__name__)


class ConfidenceService:
    
    def calculate_recommendation_confidence(
        self,
        db_session: Session,
        user: User,
        item: MenuItem,
        recommendation_session: RecommendationSession,
        base_score: float
    ) -> tuple[float, str]:
        """
        Calculate confidence score (0.0 to 1.0) for a recommendation.
        
        Returns:
            tuple: (confidence_score, confidence_explanation)
        """
        if not user or not item:
            return 0.5, "Limited information available"
        
        factors = []
        confidence_components = []
        
        profile_certainty = self._calculate_profile_certainty(db_session, user)
        factors.append(profile_certainty)
        
        if profile_certainty >= 0.7:
            confidence_components.append(f"strong understanding of your taste")
        elif profile_certainty >= 0.5:
            confidence_components.append(f"good understanding of your taste")
        else:
            confidence_components.append(f"building your taste profile")
        
        feature_completeness = self._calculate_feature_completeness(item)
        factors.append(feature_completeness)
        
        similar_items_rated = self._count_similar_items_rated(db_session, user, item)
        similarity_factor = min(1.0, similar_items_rated / 10.0)
        factors.append(similarity_factor)
        
        if similar_items_rated >= 5:
            confidence_components.append(f"{similar_items_rated} similar items you've tried")
        
        context_match = self._calculate_context_match(item, recommendation_session)
        factors.append(context_match)
        
        if context_match >= 0.8:
            confidence_components.append(f"perfect for {recommendation_session.meal_intent}")
        
        score_confidence = base_score
        factors.append(score_confidence)
        
        overall_confidence = sum(factors) / len(factors)
        overall_confidence = max(0.0, min(1.0, overall_confidence))
        
        if not confidence_components:
            explanation = "Based on your preferences"
        else:
            explanation = "Based on " + " and ".join(confidence_components[:2])
        
        return overall_confidence, explanation
    
    def _calculate_profile_certainty(self, db_session: Session, user: User) -> float:
        """
        Calculate how certain we are about user's taste profile.
        Based on number of ratings and feedback given.
        """
        rating_count = len(db_session.exec(
            select(Rating).where(Rating.user_id == user.id)
        ).all())
        
        interaction_count = len(db_session.exec(
            select(UserItemInteractionHistory).where(UserItemInteractionHistory.user_id == user.id)
        ).all())
        
        total_feedback = rating_count + (interaction_count * 0.5)
        
        if total_feedback >= 50:
            return 1.0
        elif total_feedback >= 20:
            return 0.8
        elif total_feedback >= 10:
            return 0.6
        elif total_feedback >= 5:
            return 0.4
        else:
            return 0.3
    
    def _calculate_feature_completeness(self, item: MenuItem) -> float:
        """
        Calculate how complete the item's feature data is.
        Better features = higher confidence.
        """
        completeness_score = 0.0
        total_checks = 0
        
        if item.features:
            taste_features = item.features.get("taste", {})
            if taste_features:
                completeness_score += 0.3
            total_checks += 0.3
            
            texture_features = item.features.get("texture", {})
            if texture_features:
                completeness_score += 0.2
            total_checks += 0.2
        
        if item.cuisine and len(item.cuisine) > 0:
            completeness_score += 0.2
            total_checks += 0.2
        
        if item.ingredients and len(item.ingredients) > 0:
            completeness_score += 0.15
            total_checks += 0.15
        
        if item.description:
            completeness_score += 0.15
            total_checks += 0.15
        
        if total_checks == 0:
            return 0.5
        
        return completeness_score / total_checks
    
    def _count_similar_items_rated(
        self,
        db_session: Session,
        user: User,
        item: MenuItem
    ) -> int:
        """
        Count how many items with similar cuisine/features user has rated.
        More rated similar items = higher confidence.
        """
        if not item.cuisine:
            return 0
        
        all_ratings = db_session.exec(
            select(Rating).where(Rating.user_id == user.id)
        ).all()
        
        similar_count = 0
        for rating in all_ratings:
            try:
                rated_item = db_session.get(MenuItem, rating.item_id)
                if rated_item and rated_item.cuisine:
                    if any(cuisine in rated_item.cuisine for cuisine in item.cuisine):
                        similar_count += 1
            except Exception:
                continue
        
        return similar_count
    
    def _calculate_context_match(
        self,
        item: MenuItem,
        recommendation_session: RecommendationSession
    ) -> float:
        """
        Calculate how well item matches the current context.
        """
        match_score = 0.5
        
        if item.course:
            meal_intent_course_map = {
                "appetizer": ["appetizer", "starter"],
                "main_course": ["main", "entree"],
                "dessert": ["dessert", "sweet"],
                "snack": ["appetizer", "side"],
                "beverage": ["beverage", "drink"]
            }
            
            expected_courses = meal_intent_course_map.get(
                recommendation_session.meal_intent,
                []
            )
            
            if item.course.lower() in expected_courses:
                match_score = 1.0
            elif item.course.lower() in ["main", "entree", "appetizer"]:
                match_score = 0.7
        
        if recommendation_session.budget and item.price:
            if item.price <= recommendation_session.budget:
                match_score = min(1.0, match_score + 0.2)
            elif item.price <= recommendation_session.budget * 1.2:
                match_score = min(1.0, match_score + 0.1)
        
        return match_score
    
    def get_novelty_indicator(
        self,
        user_history: Optional[UserItemInteractionHistory]
    ) -> str:
        """
        Get a user-friendly indicator of item novelty.
        """
        if not user_history:
            return "new_to_you"
        
        if user_history.was_ordered and user_history.was_liked:
            return "similar_to_favorites"
        
        if user_history.times_shown == 0:
            return "new_to_you"
        elif user_history.times_shown <= 2:
            return "new_to_you"
        else:
            return "popular"
