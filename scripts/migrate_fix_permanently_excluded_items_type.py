"""
Migration: Fix permanently_excluded_items column type from TEXT to JSONB

This script converts the permanently_excluded_items column from TEXT to JSONB.
Safe to run multiple times - checks column type before altering.
"""

from sqlalchemy import text, inspect
from config.database import engine
from utils.logger import setup_logger

logger = setup_logger(__name__)


def column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    try:
        columns = [col["name"] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception:
        return False


def get_column_type(table_name: str, column_name: str) -> str:
    inspector = inspect(engine)
    try:
        columns = inspector.get_columns(table_name)
        for col in columns:
            if col["name"] == column_name:
                return str(col["type"])
        return ""
    except Exception:
        return ""


def fix_permanently_excluded_items_type():
    table_name = "user"
    column_name = "permanently_excluded_items"
    
    if not column_exists(table_name, column_name):
        logger.info(f"Column '{column_name}' does not exist in {table_name} table yet")
        return
    
    col_type = get_column_type(table_name, column_name)
    
    if "JSON" in col_type.upper():
        logger.info(f"Column '{column_name}' is already JSONB type: {col_type}")
        return
    
    logger.info(f"Converting '{column_name}' from {col_type} to JSONB")
    
    with engine.connect() as conn:
        # Step 1: Drop the default
        conn.execute(text(f"""
            ALTER TABLE "{table_name}" 
            ALTER COLUMN {column_name} DROP DEFAULT
        """))
        
        # Step 2: Convert TEXT to JSONB using USING clause to parse the JSON text
        conn.execute(text(f"""
            ALTER TABLE "{table_name}" 
            ALTER COLUMN {column_name} TYPE JSONB 
            USING {column_name}::jsonb
        """))
        
        # Step 3: Set new JSONB default
        conn.execute(text(f"""
            ALTER TABLE "{table_name}" 
            ALTER COLUMN {column_name} SET DEFAULT '[]'::jsonb
        """))
        
        conn.commit()
    
    logger.info(f"Successfully converted '{column_name}' to JSONB type")


if __name__ == "__main__":
    fix_permanently_excluded_items_type()
