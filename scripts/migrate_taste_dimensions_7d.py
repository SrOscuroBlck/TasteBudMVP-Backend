from __future__ import annotations
import sys  
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select, text
from config.database import engine
from models.user import User, TASTE_AXES
from models.restaurant import MenuItem
from typing import Dict


class TasteDimensionMigrationError(Exception):
    pass


def migrate_taste_dimensions_to_7d(dry_run: bool = False) -> Dict[str, int]:
    if not dry_run:
        print("MIGRATING TASTE DIMENSIONS FROM 10D TO 7D")
        print("This will update all users and menu items")
        confirmation = input("Continue? (yes/no): ")
        if confirmation.lower() != "yes":
            raise TasteDimensionMigrationError("Operation cancelled by user")
    
    stats = {
        "users_migrated":0,
        "items_migrated": 0,
        "tables_altered": 0
    }
    
    if not dry_run:
        alter_database_schema()
        stats["tables_altered"] = 2
    
    with Session(engine) as session:
        users = session.exec(select(User)).all()
        items = session.exec(select(MenuItem)).all()
        
        print(f"\nFound {len(users)} users and {len(items)} items to migrate")
        
        for user in users:
            user.taste_vector = convert_10d_to_7d(user.taste_vector)
            user.taste_uncertainty = convert_10d_to_7d(user.taste_uncertainty)
            
            if not dry_run:
                session.add(user)
            
            stats["users_migrated"] += 1
        
        for item in items:
            item.features = convert_10d_to_7d(item.features)
           
            item.texture = extract_texture_from_10d(item.features)
            item.richness = estimate_richness_from_10d(item.features)
            
            if not dry_run:
                session.add(item)
            
            stats["items_migrated"] += 1
        
        if not dry_run:
            session.commit()
    
    return stats


def alter_database_schema() -> None:
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE menuitem ADD COLUMN IF NOT EXISTS texture JSONB DEFAULT \'{}\''))
        conn.execute(text('ALTER TABLE menuitem ADD COLUMN IF NOT EXISTS richness FLOAT'))


def convert_10d_to_7d(vector_10d: Dict[str, float]) -> Dict[str, float]:
    if not vector_10d:
        return {axis: 0.5 for axis in TASTE_AXES}
    
    vector_7d = {}
    
    old_to_new_mapping = {
        "sweet": "sweet",
        "sour": "sour",
        "salty": "salty",
        "bitter": "bitter",
        "umami": "umami",
        "spicy": "spicy",
        "fattiness": "fatty"
    }
    
    for old_axis, new_axis in old_to_new_mapping.items():
        if old_axis in vector_10d:
            vector_7d[new_axis] = vector_10d[old_axis]
        else:
            vector_7d[new_axis] = 0.5
    
    if "acidity" in vector_10d and "sour" in vector_7d:
        vector_7d["sour"] = (vector_7d["sour"] + vector_10d["acidity"]) / 2.0
    
    if "temp_hot" in vector_10d and "spicy" in vector_7d:
        if vector_10d.get("temp_hot", 0.5) > 0.7:
            boost = (vector_10d["temp_hot"] - 0.5) * 0.3
            vector_7d["spicy"] = min(1.0, vector_7d["spicy"] + boost)
    
    for axis in TASTE_AXES:
        if axis not in vector_7d:
            vector_7d[axis] = 0.5
        
        vector_7d[axis] = max(0.0, min(1.0, vector_7d[axis]))
    
    return vector_7d


def extract_texture_from_10d(features_10d: Dict[str, float]) -> Dict[str, float]:
    texture = {}
    
    if "crunch" in features_10d and features_10d["crunch"] >= 0.6:
        texture["crunchy"] = features_10d["crunch"]
    
    if "fattiness" in features_10d and features_10d["fattiness"] >= 0.7:
        texture["creamy"] = min(1.0, features_10d["fattiness"] * 0.8)
    
    return texture


def estimate_richness_from_10d(features_10d: Dict[str, float]) -> float:
    if not features_10d:
        return 0.5
    
    fattiness = features_10d.get("fattiness", 0.0)
    umami = features_10d.get("umami", 0.0)
    sweet = features_10d.get("sweet", 0.0)
    
    richness = (fattiness * 0.6) + (umami * 0.25) + (sweet * 0.15)
    
    return max(0.0, min(1.0, richness))


def print_migration_stats(stats: Dict[str, int]) -> None:
    print("\n" + "="*60)
    print("MIGRATION STATISTICS")
    print("="*60)
    print(f"Database tables altered: {stats['tables_altered']}")
    print(f"Users migrated:          {stats['users_migrated']}")
    print(f"Menu items migrated:     {stats['items_migrated']}")
    print("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Migrate taste dimensions from 10D to 7D"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    
    args = parser.parse_args()
    
    try:
        stats = migrate_taste_dimensions_to_7d(dry_run=args.dry_run)
        print_migration_stats(stats)
        
        if args.dry_run:
            print("\nDRY RUN COMPLETED - No changes were made")
        else:
            print("\nMIGRATION COMPLETED SUCCESSFULLY")
            print("\nNOTE: You should regenerate taste vectors for all items using:")
            print("  python scripts/regenerate_taste_vectors_llm.py")
    
    except TasteDimensionMigrationError as e:
        print(f"\nError: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)
