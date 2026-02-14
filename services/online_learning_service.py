from __future__ import annotations
from typing import Optional
from uuid import UUID
import numpy as np
from sqlmodel import Session
from models import User, MenuItem
from models.session import PostMealFeedback, RecommendationSession
from utils.logger import setup_logger

logger = setup_logger(__name__)


class OnlineLearningService:
    
    def __init__(self):
        self.new_user_learning_rate = 0.3
        self.learning_user_learning_rate = 0.15
        self.established_user_learning_rate = 0.05
        
        self.taste_match_weight = 0.5
        self.satisfaction_weight = 0.3
        self.reorder_weight = 0.2
    
    def update_from_post_meal_feedback(
        self,
        db_session: Session,
        user: User,
        feedback: PostMealFeedback,
        session: RecommendationSession
    ) -> None:
        if not user:
            raise ValueError("user is required for online learning")
        
        if not feedback:
            raise ValueError("feedback is required for online learning")
        
        if not session:
            raise ValueError("session is required for online learning")
        
        experience_level = self._get_user_experience_level(user)
        learning_rate = self._get_learning_rate(experience_level)
        
        overall_signal = self._calculate_overall_signal(feedback)
        
        self._update_taste_vector(db_session, user, feedback, overall_signal, learning_rate)
        
        self._update_uncertainty(user, experience_level)
        
        self._update_cuisine_affinity(user, session, feedback, learning_rate)
        
        db_session.add(user)
        db_session.commit()
        
        logger.info(
            "User profile updated from post-meal feedback",
            extra={
                "user_id": str(user.id),
                "session_id": str(session.id),
                "overall_signal": round(overall_signal, 3),
                "learning_rate": learning_rate,
                "experience_level": experience_level
            }
        )
    
    def _get_user_experience_level(self, user: User) -> str:
        from sqlmodel import select, func
        from models.feedback import Rating
        
        if not hasattr(user, "id"):
            return "new"
        
        return "learning"
    
    def _get_learning_rate(self, experience_level: str) -> float:
        rates = {
            "new": self.new_user_learning_rate,
            "learning": self.learning_user_learning_rate,
            "established": self.established_user_learning_rate
        }
        return rates.get(experience_level, self.learning_user_learning_rate)
    
    def _calculate_overall_signal(self, feedback: PostMealFeedback) -> float:
        if not feedback:
            return 0.0
        
        taste_normalized = (feedback.taste_match - 3) / 2.0
        satisfaction_normalized = (feedback.overall_satisfaction - 3) / 2.0
        reorder_signal = 1.0 if feedback.would_order_again else -0.5
        
        overall_signal = (
            self.taste_match_weight * taste_normalized +
            self.satisfaction_weight * satisfaction_normalized +
            self.reorder_weight * reorder_signal
        )
        
        return max(-1.0, min(1.0, overall_signal))
    
    def _update_taste_vector(
        self,
        db_session: Session,
        user: User,
        feedback: PostMealFeedback,
        overall_signal: float,
        learning_rate: float
    ) -> None:
        if not feedback.items_ordered or len(feedback.items_ordered) == 0:
            return
        
        item_features = []
        
        for item_id in feedback.items_ordered:
            item = db_session.get(MenuItem, item_id)
            if item and item.features:
                item_features.append(item.features)
        
        if not item_features:
            logger.warning("No item features found for taste vector update")
            return
        
        avg_features = np.mean(item_features, axis=0)
        
        if user.taste_vector is None or len(user.taste_vector) == 0:
            user.taste_vector = avg_features.tolist()
        else:
            current_vector = np.array(user.taste_vector)
            
            if len(current_vector) != len(avg_features):
                logger.warning(
                    "Feature dimension mismatch",
                    extra={
                        "user_vector_dim": len(current_vector),
                        "item_features_dim": len(avg_features)
                    }
                )
                return
            
            adjustment = learning_rate * overall_signal * (avg_features - current_vector)
            
            new_vector = current_vector + adjustment
            
            user.taste_vector = new_vector.tolist()
        
        logger.info(
            "Taste vector updated",
            extra={
                "user_id": str(user.id),
                "signal": round(overall_signal, 3),
                "learning_rate": learning_rate,
                "items_processed": len(item_features)
            }
        )
    
    def _update_uncertainty(self, user: User, experience_level: str) -> None:
        if user.taste_uncertainty is None:
            user.taste_uncertainty = 1.0
        
        decay_rates = {
            "new": 0.95,
            "learning": 0.90,
            "established": 0.85
        }
        decay_rate = decay_rates.get(experience_level, 0.90)
        
        min_uncertainty = 0.1
        user.taste_uncertainty = max(min_uncertainty, user.taste_uncertainty * decay_rate)
    
    def _update_cuisine_affinity(
        self,
        user: User,
        session: RecommendationSession,
        feedback: PostMealFeedback,
        learning_rate: float
    ) -> None:
        from models import MenuItem
        
        if user.cuisine_affinity is None:
            user.cuisine_affinity = {}
        
        cuisines_in_meal = set()
        
        for item_id in feedback.items_ordered:
            from sqlmodel import Session as DBSession
            
            if hasattr(session, "get"):
                item = session.get(MenuItem, item_id)
            else:
                continue
            
            if item and item.cuisine:
                cuisines_in_meal.update(item.cuisine)
        
        if not cuisines_in_meal:
            return
        
        overall_signal = self._calculate_overall_signal(feedback)
        
        for cuisine in cuisines_in_meal:
            current_affinity = user.cuisine_affinity.get(cuisine, 0.0)
            
            adjustment = learning_rate * overall_signal
            new_affinity = current_affinity + adjustment
            
            new_affinity = max(-1.0, min(1.0, new_affinity))
            
            user.cuisine_affinity[cuisine] = new_affinity
        
        logger.info(
            "Cuisine affinity updated",
            extra={
                "user_id": str(user.id),
                "cuisines": list(cuisines_in_meal),
                "signal": round(overall_signal, 3)
            }
        )
    
    def decay_old_preferences(self, user: User, decay_factor: float = 0.98) -> None:
        if not user:
            return
        
        if user.taste_vector and len(user.taste_vector) > 0:
            taste_array = np.array(user.taste_vector)
            decayed_vector = taste_array * decay_factor
            user.taste_vector = decayed_vector.tolist()
        
        if user.cuisine_affinity:
            for cuisine in user.cuisine_affinity:
                user.cuisine_affinity[cuisine] *= decay_factor


online_learning_service = OnlineLearningService()
