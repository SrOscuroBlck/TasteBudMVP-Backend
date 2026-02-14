from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from config.database import engine
from models.user import User, TASTE_AXES
from models.session import RecommendationFeedback, FeedbackType
from models.restaurant import MenuItem
from services.unified_feedback_service import temporal_weight
from services.features import clamp01


class ProfileRecomputationError(Exception):
    pass


def recompute_all_profiles_with_decay(dry_run: bool = False) -> Dict[str, int]:
    if not dry_run:
        print("RECOMPUTING ALL USER PROFILES WITH TEMPORAL DECAY")
        confirmation = input("This will overwrite existing taste vectors. Continue? (yes/no): ")
        if confirmation.lower() != "yes":
            raise ProfileRecomputationError("Operation cancelled by user")
    
    with Session(engine) as session:
        users = session.exec(select(User)).all()
        
        if not users:
            raise ProfileRecomputationError("No users found in database")
        
        print(f"\nFound {len(users)} users to recompute")
        
        stats = {
            "users_processed": 0,
            "users_updated": 0,
            "total_feedback_processed": 0
        }
        
        for user in users:
            result = recompute_single_user_profile(session, user, dry_run)
            
            if result["updated"]:
                stats["users_updated"] += 1
            
            stats["users_processed"] += 1
            stats["total_feedback_processed"] += result["feedback_count"]
            
            if not dry_run and result["updated"]:
                session.add(user)
        
        if not dry_run:
            session.commit()
        
        return stats


def recompute_single_user_profile(
    session: Session,
    user: User,
    dry_run: bool
) -> Dict[str, any]:
    feedback_records = session.exec(
        select(RecommendationFeedback)
        .where(RecommendationFeedback.session_id.in_(
            select(RecommendationFeedback.session_id)
            .where(RecommendationFeedback.item_id.in_(
                select(MenuItem.id)
            ))
        ))
    ).all()
    
    user_feedback = [
        fb for fb in feedback_records
        if str(fb.session_id) in get_user_session_ids(session, user.id)
    ]
    
    if not user_feedback:
        return {"updated": False, "feedback_count": 0}
    
    new_taste_vector = {axis: 0.5 for axis in TASTE_AXES}
    new_uncertainty = {axis: 0.5 for axis in TASTE_AXES}
    new_cuisine_affinity = {}
    
    weighted_contributions = defaultdict(list)
    cuisine_contributions = defaultdict(list)
    
    for feedback in sorted(user_feedback, key=lambda f: f.timestamp):
        item = session.get(MenuItem, feedback.item_id)
        
        if not item or not item.features:
            continue
        
        weight = temporal_weight(feedback.timestamp)
        
        feedback_type = FeedbackType(feedback.feedback_type)
        is_positive = feedback_type in [FeedbackType.LIKE, FeedbackType.SELECTED]
        
        direction = 1.0 if is_positive else -1.0
        
        for axis, value in item.features.items():
            if axis in TASTE_AXES and value > 0.5:
                weighted_contributions[axis].append((weight, direction * value))
        
        for cuisine in item.cuisine:
            cuisine_contributions[cuisine].append((weight, direction))
    
    for axis in TASTE_AXES:
        if axis in weighted_contributions:
            contributions = weighted_contributions[axis]
            
            total_weight = sum(w for w, _ in contributions)
            weighted_sum = sum(w * val for w, val in contributions)
            
            if total_weight > 0:
                adjustment = weighted_sum / total_weight
                new_taste_vector[axis] = clamp01(0.5 + adjustment * 0.3)
                
                new_uncertainty[axis] = max(0.1, 0.5 - (total_weight * 0.1))
    
    for cuisine in cuisine_contributions:
        contributions = cuisine_contributions[cuisine]
        
        total_weight = sum(w for w, _ in contributions)
        weighted_sum = sum(w * direction for w, direction in contributions)
        
        if total_weight > 0:
            affinity = clamp01(0.5 + (weighted_sum / total_weight) * 0.3)
            new_cuisine_affinity[cuisine] = affinity
    
    if not dry_run:
        user.taste_vector = new_taste_vector
        user.taste_uncertainty = new_uncertainty
        user.cuisine_affinity = new_cuisine_affinity
        user.last_updated = datetime.utcnow()
    
    return {"updated": True, "feedback_count": len(user_feedback)}


def get_user_session_ids(session: Session, user_id) -> List[str]:
    from models.session import RecommendationSession
    
    sessions = session.exec(
        select(RecommendationSession)
        .where(RecommendationSession.user_id == user_id)
    ).all()
    
    return [str(s.id) for s in sessions]


def print_recomputation_stats(stats: Dict[str, int]) -> None:
    print("\n" + "="*60)
    print("PROFILE RECOMPUTATION STATISTICS")
    print("="*60)
    print(f"Users processed:       {stats['users_processed']}")
    print(f"Users updated:         {stats['users_updated']}")
    print(f"Total feedback items:  {stats['total_feedback_processed']}")
    print("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Recompute user profiles with temporal feedback decay"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    
    args = parser.parse_args()
    
    try:
        stats = recompute_all_profiles_with_decay(dry_run=args.dry_run)
        print_recomputation_stats(stats)
        
        if args.dry_run:
            print("\nDRY RUN COMPLETED - No changes were made")
        else:
            print("\nPROFILE RECOMPUTATION COMPLETED SUCCESSFULLY")
    
    except ProfileRecomputationError as e:
        print(f"\nError: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
