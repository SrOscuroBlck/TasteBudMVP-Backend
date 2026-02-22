"""
Add composition tracking fields to RecommendationSession table.
Uses existing RecommendationFeedback table - no new table needed.

New fields:
- recommendationsession.active_composition_id (VARCHAR) - tracks current composition
- recommendationsession.composition_validation_state (JSON) - temp cache for partial regeneration
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from sqlmodel import Session, text
from config.database import engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    logger.info("Adding composition tracking to RecommendationSession...")
    
    with Session(engine) as session:
        try:
            logger.info("Adding active_composition_id column...")
            session.exec(text("""
                ALTER TABLE recommendationsession 
                ADD COLUMN IF NOT EXISTS active_composition_id VARCHAR;
            """))
            
            logger.info("Adding composition_validation_state column...")
            session.exec(text("""
                ALTER TABLE recommendationsession 
                ADD COLUMN IF NOT EXISTS composition_validation_state JSON DEFAULT '{}';
            """))
            
            session.commit()
            logger.info("Migration completed successfully!")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Migration failed: {e}", exc_info=True)
            raise


def verify_migration():
    logger.info("Verifying migration...")
    
    with Session(engine) as session:
        result = session.exec(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'recommendationsession' 
            AND column_name IN ('active_composition_id', 'composition_validation_state');
        """))
        columns = [row[0] for row in result]
        
        if 'active_composition_id' in columns and 'composition_validation_state' in columns:
            logger.info("Columns added successfully")
            return True
        else:
            logger.error(f"Missing columns. Found: {columns}")
            return False


if __name__ == "__main__":
    print("="*60)
    print("COMPOSITION FEEDBACK MIGRATION")
    print("="*60)
    print("\nAdding composition tracking to existing session table...")
    print("Using existing RecommendationFeedback for detailed feedback.\n")
    
    try:
        run_migration()
        if verify_migration():
            print("\n" + "="*60)
            print("MIGRATION COMPLETE")
            print("="*60)
            print("\nDatabase ready for composition feedback testing!")
        else:
            sys.exit(1)
    except Exception as e:
        print("\n" + "="*60)
        print("MIGRATION FAILED")
        print("="*60)
        print(f"\nError: {e}")
        sys.exit(1)

