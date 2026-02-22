from __future__ import annotations
from typing import Optional, Dict
from datetime import datetime
from uuid import UUID
from sqlmodel import Session, select

from models.bayesian_profile import BayesianTasteProfile
from models.user import User, TASTE_AXES
from models.restaurant import MenuItem
from models.session import FeedbackType
from utils.logger import setup_logger
from config.settings import settings

logger = setup_logger(__name__)


class BayesianProfileService:
    
    def get_or_create_profile(self, db_session: Session, user: User) -> BayesianTasteProfile:
        if not user:
            raise ValueError("user is required to get or create profile")
        
        statement = select(BayesianTasteProfile).where(
            BayesianTasteProfile.user_id == user.id
        )
        profile = db_session.exec(statement).first()
        
        if profile:
            return profile
        
        profile = self.create_profile_from_user(db_session, user)
        db_session.add(profile)
        db_session.commit()
        db_session.refresh(profile)
        
        logger.info(
            "Created new Bayesian profile",
            extra={"user_id": str(user.id), "profile_id": str(profile.id)}
        )
        
        return profile
    
    def create_profile_from_user(self, db_session: Session, user: User) -> BayesianTasteProfile:
        if not user:
            raise ValueError("user is required to create profile")
        
        profile = BayesianTasteProfile(user_id=user.id)
        
        prior_strength = 10.0
        
        for axis in TASTE_AXES:
            mean_value = user.taste_vector.get(axis, 0.5)
            uncertainty = user.taste_uncertainty.get(axis, 0.5)
            
            if uncertainty > 0:
                effective_strength = prior_strength / uncertainty
            else:
                effective_strength = prior_strength * 2
            
            profile.alpha_params[axis] = mean_value * effective_strength
            profile.beta_params[axis] = (1.0 - mean_value) * effective_strength
        
        for cuisine, affinity in user.cuisine_affinity.items():
            profile.cuisine_alpha[cuisine] = affinity * prior_strength
            profile.cuisine_beta[cuisine] = (1.0 - affinity) * prior_strength
        
        profile.update_cached_statistics()
        
        return profile
    
    def create_profile_from_archetype(
        self,
        db_session: Session,
        user: User,
        archetype_taste_vector: Dict[str, float]
    ) -> BayesianTasteProfile:
        if not user:
            raise ValueError("user is required to create profile from archetype")
        
        if not archetype_taste_vector:
            raise ValueError("archetype_taste_vector is required")
        
        profile = BayesianTasteProfile(user_id=user.id)
        
        prior_strength = 10.0
        
        for axis in TASTE_AXES:
            mean_value = archetype_taste_vector.get(axis, 0.5)
            profile.alpha_params[axis] = mean_value * prior_strength
            profile.beta_params[axis] = (1.0 - mean_value) * prior_strength
        
        profile.update_cached_statistics()
        
        return profile
    
    def update_from_feedback(
        self,
        db_session: Session,
        profile: BayesianTasteProfile,
        item: MenuItem,
        feedback_type: FeedbackType,
        feedback_timestamp: datetime
    ) -> None:
        if not profile:
            raise ValueError("profile is required for update")
        
        if not item:
            raise ValueError("item is required for feedback update")
        
        if not feedback_type:
            raise ValueError("feedback_type is required")
        
        from services.learning.unified_feedback_service import temporal_weight
        
        temporal_w = temporal_weight(
            feedback_timestamp,
            settings.FEEDBACK_HALF_LIFE_DAYS
        )
        
        is_positive = feedback_type in [
            FeedbackType.LIKE,
            FeedbackType.SELECTED,
            FeedbackType.ACCEPTED,  # User ordered this item
            FeedbackType.SAVE_FOR_LATER
        ]
        
        is_negative = feedback_type in [
            FeedbackType.DISLIKE,
            FeedbackType.SKIP  # User rejected this in composition
        ]
        
        # Only update if we have clear positive or negative signal
        if not is_positive and not is_negative:
            logger.warning(
                "Ambiguous feedback type, skipping Bayesian update",
                extra={"feedback_type": feedback_type.value}
            )
            return
        
        self._update_taste_parameters(profile, item, is_positive, temporal_w)
        
        self._update_cuisine_parameters(profile, item, is_positive, temporal_w)
        
        profile.last_updated = datetime.utcnow()
        profile.update_cached_statistics()
        
        db_session.add(profile)
        
        logger.info(
            "Bayesian profile updated from feedback",
            extra={
                "profile_id": str(profile.id),
                "user_id": str(profile.user_id),
                "item_id": str(item.id),
                "feedback_type": feedback_type.value,
                "temporal_weight": round(temporal_w, 3),
                "is_positive": is_positive
            }
        )
    
    def _update_taste_parameters(
        self,
        profile: BayesianTasteProfile,
        item: MenuItem,
        is_positive: bool,
        temporal_w: float
    ) -> None:
        # Use AGGRESSIVE learning rate for negative signals
        # Positive feedback: moderate learning (users are less certain about likes)
        # Negative feedback: strong learning (users are VERY certain about dislikes)
        learning_strength = 6.0 if not is_positive else 3.0
        
        for axis in TASTE_AXES:
            feature_value = item.features.get(axis, 0.5)
            
            if axis not in profile.alpha_params:
                profile.alpha_params[axis] = 2.0
            if axis not in profile.beta_params:
                profile.beta_params[axis] = 2.0
            
            if is_positive:
                # Boost features that are strong in liked items
                profile.alpha_params[axis] += temporal_w * feature_value * learning_strength
                profile.beta_params[axis] += temporal_w * (1.0 - feature_value) * 0.3 * learning_strength
            else:
                # Penalize features that are strong in disliked items
                profile.beta_params[axis] += temporal_w * feature_value * learning_strength
                profile.alpha_params[axis] += temporal_w * (1.0 - feature_value) * 0.3 * learning_strength
    
    def _update_cuisine_parameters(
        self,
        profile: BayesianTasteProfile,
        item: MenuItem,
        is_positive: bool,
        temporal_w: float
    ) -> None:
        # Use AGGRESSIVE learning rate for cuisine preferences
        # Negative signals are stronger (user knows what they don't like)
        cuisine_learning_strength = 8.0 if not is_positive else 4.0
        
        for cuisine in item.cuisine:
            typicality = item.provenance.get("cuisine_typicality", {}).get(cuisine, 0.7)
            
            if cuisine not in profile.cuisine_alpha:
                profile.cuisine_alpha[cuisine] = 2.0
            if cuisine not in profile.cuisine_beta:
                profile.cuisine_beta[cuisine] = 2.0
            
            if is_positive:
                profile.cuisine_alpha[cuisine] += temporal_w * typicality * cuisine_learning_strength
                profile.cuisine_beta[cuisine] += temporal_w * (1.0 - typicality) * 0.2 * cuisine_learning_strength
            else:
                profile.cuisine_beta[cuisine] += temporal_w * typicality * cuisine_learning_strength
                profile.cuisine_alpha[cuisine] += temporal_w * (1.0 - typicality) * 0.2 * cuisine_learning_strength
