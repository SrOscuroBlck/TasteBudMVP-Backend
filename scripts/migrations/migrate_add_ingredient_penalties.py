"""
Migration: Add ingredient_penalties column to user table

This script adds the ingredient_penalties column to the user table if it doesn't exist.
This column tracks user's learned penalties for specific ingredients, enabling 
cross-restaurant learning (e.g., if user dislikes mozzarella in one restaurant,
all mozzarella items get penalized across all restaurants).

Safe to run multiple times - checks for table and column existence before altering.
"""

from sqlalchemy import text, inspect
from config.database import engine
from utils.logger import setup_logger
import uuid

logger = setup_logger(__name__)

# Generate correlation_id for this migration run
correlation_id = str(uuid.uuid4())


def table_exists(table_name: str) -> bool:
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    if not table_exists(table_name):
        return False
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def add_ingredient_penalties_column():
    table_name = "user"  # SQLModel uses singular form
    column_name = "ingredient_penalties"
    
    if not table_exists(table_name):
        logger.info(
            f"Table '{table_name}' does not exist yet - will be created with column by SQLModel",
            extra={"correlation_id": correlation_id}
        )
        return
    
    if column_exists(table_name, column_name):
        logger.info(
            f"Column '{column_name}' already exists in {table_name} table",
            extra={"correlation_id": correlation_id, "table": table_name, "column": column_name}
        )
        return
    
    logger.info(
        f"Adding '{column_name}' column to {table_name} table",
        extra={"correlation_id": correlation_id, "table": table_name, "column": column_name}
    )
    
    with engine.connect() as conn:
        # Quote table name since "user" is a reserved keyword in PostgreSQL
        # Use JSONB type to match SQLModel Column(JSON) type
        # Default to empty object {} for storing ingredient: penalty_value mappings
        conn.execute(text(f"""
            ALTER TABLE "{table_name}" 
            ADD COLUMN {column_name} JSONB DEFAULT '{{}}'::jsonb
        """))
        conn.commit()
    
    logger.info(
        f"Successfully added '{column_name}' column to {table_name} table",
        extra={
            "correlation_id": correlation_id,
            "table": table_name,
            "column": column_name,
            "column_type": "JSONB",
            "default_value": "{}"
        }
    )


if __name__ == "__main__":
    try:
        add_ingredient_penalties_column()
        logger.info(
            "Migration completed successfully",
            extra={"correlation_id": correlation_id}
        )
    except Exception as e:
        logger.error(
            "Migration failed",
            extra={"correlation_id": correlation_id, "error": str(e)},
            exc_info=True
        )
        raise
