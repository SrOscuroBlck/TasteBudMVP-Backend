import argparse
from sqlmodel import SQLModel

from config.database import engine, get_db
from models import (
    EvaluationMetric,
    OfflineEvaluation,
    OnlineEvaluationMetrics,
    ABTestExperiment,
    InterleavingResult
)
from utils.logger import setup_logger

logger = setup_logger(__name__)


def create_evaluation_tables(dry_run: bool = False):
    logger.info("Creating evaluation tables", extra={"dry_run": dry_run})
    
    if dry_run:
        print("Dry run - would create the following tables:")
        print("  - evaluation_metric")
        print("  - offline_evaluation")
        print("  - online_evaluation_metrics")
        print("  - ab_test_experiment")
        print("  - interleaving_result")
        return
    
    try:
        SQLModel.metadata.create_all(engine)
        
        logger.info("Evaluation tables created successfully")
        
        print("Successfully created evaluation tables:")
        print("  ✓ evaluation_metric")
        print("  ✓ offline_evaluation")
        print("  ✓ online_evaluation_metrics")
        print("  ✓ ab_test_experiment")
        print("  ✓ interleaving_result")
        
    except Exception as e:
        logger.error(
            "Failed to create evaluation tables",
            extra={"error": str(e)},
            exc_info=True
        )
        print(f"Error creating tables: {e}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create database tables for Phase 4 evaluation framework"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without making changes"
    )
    
    args = parser.parse_args()
    
    create_evaluation_tables(dry_run=args.dry_run)
