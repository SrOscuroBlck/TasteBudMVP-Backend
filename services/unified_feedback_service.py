from __future__ import annotations
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from sqlmodel import Session
from sqlalchemy.orm.attributes import flag_modified

from models import User, MenuItem, Rating, Interaction
from models.session import RecommendationFeedback, FeedbackType
from services.features import clamp01
from services.interaction_history_service import InteractionHistoryService
from utils.logger import setup_logger
from config.settings import settings

logger = setup_logger(__name__)


LEARNING_RATE_MAP = {
    "mild": 0.02,
    "medium": 0.05,
    "strong": 0.10
}


class UnifiedFeedbackService:
    def __init__(self):
        self.interaction_history_service = InteractionHistoryService()
    
    def record_session_feedback(
        self,
        db_session: Session,
        user: User,
        item: MenuItem,
        feedback_type: FeedbackType,
        session_id: UUID,
        comment: Optional[str] = None
    ) -> RecommendationFeedback:
        if not user:
            raise ValueError("user is required for feedback processing")
        
        if not item:
            raise ValueError("item is required for feedback processing")
        
        if not feedback_type:
            raise ValueError("feedback_type is required for feedback processing")
        
        intensity = self._get_feedback_intensity(feedback_type)
        
        feedback = RecommendationFeedback(
            session_id=session_id,
            item_id=item.id,
            feedback_type=feedback_type.value,
            comment=comment,
            timestamp=datetime.utcnow()
        )
        
        db_session.add(feedback)
        
        self._update_user_profile(
            user=user,
            item=item,
            feedback_type=feedback_type,
            intensity=intensity
        )
        
        user.last_updated = datetime.utcnow()
        db_session.add(user)
        db_session.commit()
        db_session.refresh(feedback)
        
        try:
            self.interaction_history_service.update_interaction_outcome(
                db_session=db_session,
                user_id=user.id,
                item_id=item.id,
                was_disliked=(feedback_type == FeedbackType.DISLIKE),
                was_liked=(feedback_type == FeedbackType.LIKE),
                was_ordered=(feedback_type == FeedbackType.SELECTED)
            )
        except Exception as e:
            logger.warning(
                "Failed to update interaction history outcome",
                extra={"error": str(e), "item_id": str(item.id)}
            )
        
        logger.info(
            "Session feedback recorded and profile updated",
            extra={
                "user_id": str(user.id),
                "item_id": str(item.id),
                "feedback_type": feedback_type.value,
                "intensity": intensity,
                "session_id": str(session_id)
            }
        )
        
        return feedback
    
    def _get_feedback_intensity(self, feedback_type: FeedbackType) -> str:
        if feedback_type == FeedbackType.LIKE:
            return "mild"
        elif feedback_type == FeedbackType.SAVE_FOR_LATER:
            return "mild"
        elif feedback_type == FeedbackType.DISLIKE:
            return "medium"
        elif feedback_type == FeedbackType.SELECTED:
            return "strong"
        return "medium"
    
    def _update_user_profile(
        self,
        user: User,
        item: MenuItem,
        feedback_type: FeedbackType,
        intensity: str
    ) -> None:
        learning_rate = LEARNING_RATE_MAP.get(intensity, 0.05)
        
        is_positive = feedback_type in [FeedbackType.LIKE, FeedbackType.SELECTED, FeedbackType.SAVE_FOR_LATER]
        is_negative = feedback_type == FeedbackType.DISLIKE
        
        if is_positive:
            for axis, value in item.features.items():
                if axis in user.taste_vector and value > 0.5:
                    delta = learning_rate * value
                    user.taste_vector[axis] = clamp01(user.taste_vector[axis] + delta)
                    user.taste_uncertainty[axis] = max(0.0, user.taste_uncertainty.get(axis, 0.5) - abs(delta))
            
            flag_modified(user, "taste_vector")
            flag_modified(user, "taste_uncertainty")
            
            for cuisine in item.cuisine:
                current = user.cuisine_affinity.get(cuisine, 0.5)
                user.cuisine_affinity[cuisine] = clamp01(current + learning_rate)
            
            flag_modified(user, "cuisine_affinity")
        
        elif is_negative:
            for axis, value in item.features.items():
                if axis in user.taste_vector and value > 0.5:
                    delta = learning_rate * value
                    user.taste_vector[axis] = clamp01(user.taste_vector[axis] - delta)
                    user.taste_uncertainty[axis] = max(0.0, user.taste_uncertainty.get(axis, 0.5) - abs(delta))
            
            flag_modified(user, "taste_vector")
            flag_modified(user, "taste_uncertainty")
            
            for cuisine in item.cuisine:
                current = user.cuisine_affinity.get(cuisine, 0.5)
                user.cuisine_affinity[cuisine] = clamp01(current - learning_rate * 0.5)
            
            flag_modified(user, "cuisine_affinity")
            
            item_id_str = str(item.id)
            logger.info(
                "Checking permanent exclusion",
                extra={
                    "user_id": str(user.id),
                    "item_id": item_id_str,
                    "intensity": intensity,
                    "feedback_type": feedback_type.value,
                    "already_excluded": item_id_str in user.permanently_excluded_items,
                    "current_exclusions_count": len(user.permanently_excluded_items)
                }
            )
            if intensity == "medium" and item_id_str not in user.permanently_excluded_items:
                user.permanently_excluded_items = user.permanently_excluded_items + [item_id_str]
                flag_modified(user, "permanently_excluded_items")
                logger.info(
                    "Item added to permanent exclusions",
                    extra={
                        "user_id": str(user.id),
                        "item_id": item_id_str,
                        "new_exclusions_count": len(user.permanently_excluded_items),
                        "all_excluded_ids": user.permanently_excluded_items,
                        "intensity": intensity
                    }
                )

        
        logger.info(
            "User profile updated from feedback",
            extra={
                "user_id": str(user.id),
                "feedback_type": feedback_type.value,
                "intensity": intensity,
                "is_positive": is_positive,
                "is_negative": is_negative
            }
        )
    
    def add_rating(
        self,
        db_session: Session,
        user: User,
        item_id: str,
        rating: int,
        liked: bool,
        reasons: List[str],
        comment: str = ""
    ) -> Rating:
        item = db_session.get(MenuItem, UUID(item_id))
        if not item:
            raise ValueError(f"MenuItem {item_id} not found")
        
        rating_record = Rating(
            user_id=user.id,
            item_id=item.id,
            rating=rating,
            liked=liked,
            reasons=",".join(reasons),
            comment=comment
        )
        db_session.add(rating_record)
        
        is_positive = liked or rating >= 4
        is_negative = rating <= 2
        intensity = "strong" if is_positive else "medium" if is_negative else "mild"
        learning_rate = LEARNING_RATE_MAP.get(intensity, 0.05)
        
        if is_positive:
            for axis, value in item.features.items():
                if axis in user.taste_vector and value > 0.5:
                    delta = learning_rate * value
                    user.taste_vector[axis] = clamp01(user.taste_vector[axis] + delta)
                    user.taste_uncertainty[axis] = max(0.0, user.taste_uncertainty.get(axis, 0.5) - abs(delta))
            
            for cuisine in item.cuisine:
                current = user.cuisine_affinity.get(cuisine, 0.5)
                user.cuisine_affinity[cuisine] = clamp01(current + learning_rate)
        
        elif is_negative:
            for axis, value in item.features.items():
                if axis in user.taste_vector and value > 0.5:
                    delta = learning_rate * value
                    user.taste_vector[axis] = clamp01(user.taste_vector[axis] - delta)
                    user.taste_uncertainty[axis] = max(0.0, user.taste_uncertainty.get(axis, 0.5) - abs(delta))
            
            for cuisine in item.cuisine:
                current = user.cuisine_affinity.get(cuisine, 0.5)
                user.cuisine_affinity[cuisine] = clamp01(current - learning_rate * 0.5)
        
        user.last_updated = datetime.utcnow()
        db_session.add(user)
        db_session.commit()
        db_session.refresh(rating_record)
        
        logger.info(
            "Direct rating recorded and profile updated",
            extra={
                "user_id": str(user.id),
                "item_id": str(item.id),
                "rating": rating,
                "liked": liked,
                "intensity": intensity
            }
        )
        
        return rating_record
    
    def add_interaction(
        self,
        db_session: Session,
        user: User,
        item_id: str,
        interaction_type: str
    ) -> Interaction:
        item = db_session.get(MenuItem, UUID(item_id))
        if not item:
            raise ValueError(f"MenuItem {item_id} not found")
        
        interaction = Interaction(
            user_id=user.id,
            item_id=item.id,
            type=interaction_type
        )
        db_session.add(interaction)
        db_session.commit()
        db_session.refresh(interaction)
        
        logger.info(
            "Interaction recorded",
            extra={
                "user_id": str(user.id),
                "item_id": str(item.id),
                "type": interaction_type
            }
        )
        
        return interaction
