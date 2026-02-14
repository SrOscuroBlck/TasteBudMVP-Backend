from datetime import datetime
from sqlmodel import Session, select
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.database import engine
from models import User, BayesianTasteProfile
from services.bayesian_profile_service import BayesianProfileService
from utils.logger import setup_logger

logger = setup_logger(__name__)


def migrate_user_to_bayesian(db_session: Session, user: User, dry_run: bool = False) -> BayesianTasteProfile:
    existing_statement = select(BayesianTasteProfile).where(
        BayesianTasteProfile.user_id == user.id
    )
    existing_profile = db_session.exec(existing_statement).first()
    
    if existing_profile:
        logger.info(
            "User already has Bayesian profile",
            extra={"user_id": str(user.id), "profile_id": str(existing_profile.id)}
        )
        return existing_profile
    
    service = BayesianProfileService()
    profile = service.create_profile_from_user(db_session, user)
    
    logger.info(
        "Created Bayesian profile from user",
        extra={
            "user_id": str(user.id),
            "profile_id": str(profile.id),
            "taste_dimensions": len(profile.alpha_params),
            "cuisines_tracked": len(profile.cuisine_alpha)
        }
    )
    
    if not dry_run:
        db_session.add(profile)
        db_session.commit()
        db_session.refresh(profile)
        logger.info("Bayesian profile committed to database", extra={"profile_id": str(profile.id)})
    
    return profile


def migrate_all_users(dry_run: bool = False):
    logger.info(f"Starting migration to Bayesian profiles (dry_run={dry_run})")
    
    with Session(engine) as db_session:
        statement = select(User)
        users = db_session.exec(statement).all()
        
        logger.info(f"Found {len(users)} users to migrate")
        
        migrated_count = 0
        skipped_count = 0
        
        for user in users:
            try:
                profile = migrate_user_to_bayesian(db_session, user, dry_run)
                
                if profile.id:
                    migrated_count += 1
                else:
                    skipped_count += 1
                    
            except Exception as e:
                logger.error(
                    "Failed to migrate user",
                    extra={"user_id": str(user.id), "error": str(e)},
                    exc_info=True
                )
                skipped_count += 1
        
        logger.info(
            "Migration complete",
            extra={
                "migrated": migrated_count,
                "skipped": skipped_count,
                "total": len(users),
                "dry_run": dry_run
            }
        )
        
        return migrated_count, skipped_count


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate users to Bayesian taste profiles")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without committing to database"
    )
    
    args = parser.parse_args()
    
    logger.info("="* 60)
    logger.info("BAYESIAN PROFILE MIGRATION")
    logger.info("="* 60)
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be committed")
    
    migrated, skipped = migrate_all_users(dry_run=args.dry_run)
    
    logger.info("="* 60)
    logger.info(f"MIGRATION SUMMARY: {migrated} migrated, {skipped} skipped")
    logger.info("="* 60)
    
    if args.dry_run:
        logger.info("This was a dry run. Run without --dry-run to apply changes.")
