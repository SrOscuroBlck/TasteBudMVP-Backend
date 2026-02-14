from __future__ import annotations
from sqlalchemy import text
from config.database import engine


def add_course_and_cuisine_columns():
    """Add course and cuisine columns to menuitem table for meal type filtering."""
    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='menuitem' AND column_name IN ('course', 'cuisine')
        """))
        existing_columns = {row[0] for row in result}
        
        # Add course column if it doesn't exist
        if 'course' not in existing_columns:
            conn.execute(text("""
                ALTER TABLE menuitem 
                ADD COLUMN course VARCHAR
            """))
            print("Added 'course' column to menuitem table")
        else:
            print("'course' column already exists")
        
        # Add cuisine column if it doesn't exist
        if 'cuisine' not in existing_columns:
            conn.execute(text("""
                ALTER TABLE menuitem 
                ADD COLUMN cuisine JSON
            """))
            print("Added 'cuisine' column to menuitem table")
        else:
            print("'cuisine' column already exists")
        
        conn.commit()
        print("Migration completed successfully")


if __name__ == "__main__":
    add_course_and_cuisine_columns()
