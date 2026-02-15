"""
Migration: Add performance indexes for feedback queries

Adds composite indexes to optimize the new exclusion queries in RetrievalService.
These indexes support:
- Finding user's past sessions efficiently
- Filtering feedback by type and recency
- Joining session feedback with user efficiently
"""

from sqlalchemy import text, inspect, Index
from config.database import engine
from utils.logger import setup_logger

logger = setup_logger(__name__)


def index_exists(table_name: str, index_name: str) -> bool:
    inspector = inspect(engine)
    indexes = inspector.get_indexes(table_name)
    return any(idx["name"] == index_name for idx in indexes)


def add_feedback_performance_indexes():
    indexes_to_create = [
        (
            "recommendationsession",
            "idx_session_user_started",
            "CREATE INDEX IF NOT EXISTS idx_session_user_started ON recommendationsession(user_id, started_at DESC)"
        ),
        (
            "recommendationfeedback", 
            "idx_feedback_type_timestamp",
            "CREATE INDEX IF NOT EXISTS idx_feedback_type_timestamp ON recommendationfeedback(feedback_type, timestamp DESC)"
        ),
        (
            "recommendationfeedback",
            "idx_feedback_session_type",
            "CREATE INDEX IF NOT EXISTS idx_feedback_session_type ON recommendationfeedback(session_id, feedback_type, timestamp DESC)"
        ),
        (
            "rating",
            "idx_rating_user_timestamp",
            "CREATE INDEX IF NOT EXISTS idx_rating_user_timestamp ON rating(user_id, timestamp DESC)"
        )
    ]
    
    with engine.connect() as conn:
        for table_name, index_name, create_sql in indexes_to_create:
            if index_exists(table_name, index_name):
                logger.info(f"Index '{index_name}' already exists on {table_name}")
                continue
            
            logger.info(f"Creating index '{index_name}' on {table_name}")
            conn.execute(text(create_sql))
            conn.commit()
            logger.info(f"Successfully created index '{index_name}'")


if __name__ == "__main__":
    add_feedback_performance_indexes()
