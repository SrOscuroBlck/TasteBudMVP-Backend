"""
Migration: Add permanently_excluded_items column to users table

This script adds the permanently_excluded_items column to the users table if it doesn't exist.
Safe to run multiple times - checks for table and column existence before altering.
"""

from sqlalchemy import text, inspect
from config.database import engine
from utils.logger import setup_logger

logger = setup_logger(__name__)


def table_exists(table_name: str) -> bool:
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    if not table_exists(table_name):
        return False
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def add_permanently_excluded_items_column():
    table_name = "user"  # SQLModel uses singular form
    
    if not table_exists(table_name):
        logger.info(f"Table '{table_name}' does not exist yet - will be created with column by SQLModel")
        return
    
    if column_exists(table_name, "permanently_excluded_items"):
        logger.info(f"Column 'permanently_excluded_items' already exists in {table_name} table")
        return
    
    logger.info(f"Adding 'permanently_excluded_items' column to {table_name} table")
    
    with engine.connect() as conn:
        # Quote table name since "user" is a reserved keyword in PostgreSQL
        # Use JSONB type to match SQLModel Column(JSON) type
        conn.execute(text(f"""
            ALTER TABLE "{table_name}" 
            ADD COLUMN permanently_excluded_items JSONB DEFAULT '[]'::jsonb
        """))
        conn.commit()
    
    logger.info(f"Successfully added 'permanently_excluded_items' column to {table_name} table")


if __name__ == "__main__":
    add_permanently_excluded_items_column()
