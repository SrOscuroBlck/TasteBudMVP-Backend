"""Bootstrap Rating records from onboarding answers.

Converts onboarding likes/dislikes into actual ratings for ML training.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from uuid import UUID
from sqlmodel import Session, select

from config.database import get_session
from models import User, OnboardingAnswer, MenuItem, Rating
from utils.logger import setup_logger

logger = setup_logger(__name__)


def bootstrap_ratings_from_onboarding(user_id: str):
    """Convert onboarding answers to ratings."""
    
    with next(get_session()) as session:
        user = session.get(User, UUID(user_id))
        if not user:
            logger.error(f"User {user_id} not found")
            return
        
        # Get all onboarding answers
        answers = session.exec(
            select(OnboardingAnswer)
            .where(OnboardingAnswer.user_id == user.id)
        ).all()
        
        logger.info(f"Found {len(answers)} onboarding answers")
        
        if not answers:
            logger.error("No onboarding data found")
            return
        
        # Convert to ratings
        created_count = 0
        for answer in answers:
            # Parse the chosen_option_id to get item_id and action
            # Format: "like:<item_id>" or "dislike:<item_id>"
            parts = answer.chosen_option_id.split(":")
            if len(parts) != 2:
                logger.warning(f"Invalid option format: {answer.chosen_option_id}")
                continue
            
            action, item_id_str = parts
            
            try:
                item_id = UUID(item_id_str)
            except ValueError:
                logger.warning(f"Invalid UUID: {item_id_str}")
                continue
            
            # Check if item exists
            item = session.get(MenuItem, item_id)
            if not item:
                logger.warning(f"Item {item_id} not found")
                continue
            
            # Check if rating already exists
            existing = session.exec(
                select(Rating)
                .where(Rating.user_id == user.id)
                .where(Rating.item_id == item_id)
            ).first()
            
            if existing:
                logger.debug(f"Rating already exists for item {item_id}")
                continue
            
            # Create rating
            if action == "like":
                rating_value = 5
                liked = True
                reasons = "onboarding_like"
            elif action == "dislike":
                rating_value = 1
                liked = False
                reasons = "onboarding_dislike"
            else:
                logger.warning(f"Unknown action: {action}")
                continue
            
            rating = Rating(
                user_id=user.id,
                item_id=item_id,
                rating=rating_value,
                liked=liked,
                reasons=reasons,
                comment="Bootstrapped from onboarding",
                timestamp=answer.timestamp
            )
            
            session.add(rating)
            created_count += 1
            logger.info(f"Created rating: {action} for {item.name}")
        
        session.commit()
        logger.info(f"✅ Created {created_count} ratings from onboarding data")
        
        # Show final count
        total_ratings = session.exec(
            select(Rating)
            .where(Rating.user_id == user.id)
        ).all()
        logger.info(f"Total ratings for user: {len(total_ratings)}")


if __name__ == "__main__":
    user_id = "385b70e4-35f6-4d8e-9113-d1ef1672afec"
    
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
    
    logger.info(f"Bootstrapping ratings for user {user_id}")
    bootstrap_ratings_from_onboarding(user_id)
    logger.info("Done!")
