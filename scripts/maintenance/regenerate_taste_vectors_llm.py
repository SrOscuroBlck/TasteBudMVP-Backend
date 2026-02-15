from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select
from config.database import engine
from models.restaurant import MenuItem
from services.features.llm_features import generate_llm_taste_profile
from typing import Dict


class LLMTasteVectorRegenerationError(Exception):
    pass


def regenerate_all_taste_vectors_with_llm(dry_run: bool = False) -> Dict[str, int]:
    if not dry_run:
        print("REGENERATING ALL TASTE VECTORS WITH LLM")
        print("This will update all menu items with LLM-generated taste profiles")
        confirmation = input("Continue? (yes/no): ")
        if confirmation.lower() != "yes":
            raise LLMTasteVectorRegenerationError("Operation cancelled by user")
    
    with Session(engine) as session:
        items = session.exec(select(MenuItem)).all()
        
        if not items:
            raise LLMTasteVectorRegenerationError("No menu items found in database")
        
        print(f"\nFound {len(items)} items to process")
        
        stats = {
            "total": len(items),
            "llm_generated": 0,
            "cached": 0,
            "failed": 0,
            "skipped": 0
        }
        
        for idx, item in enumerate(items, 1):
            if idx % 10 == 0:
                print(f"Progress: {idx}/{len(items)}")
            
            result = regenerate_single_item_profile(item, dry_run)
            stats[result] += 1
            
            if not dry_run and result == "llm_generated":
                session.add(item)
                if idx % 50 == 0:
                    session.commit()
        
        if not dry_run:
            session.commit()
        
        return stats


def regenerate_single_item_profile(item: MenuItem, dry_run: bool) -> str:
    cached_profile = extract_cached_llm_profile(item)
    
    if cached_profile:
        return "cached"
    
    if not item.name and not item.description:
        return "skipped"
    
    taste, texture, richness, cuisine_typicality = generate_llm_taste_profile(
        item.name,
        item.description,
        item.ingredients if item.ingredients else [],
        item.cuisine if item.cuisine else []
    )
    
    if not taste:
        return "failed"
    
    if not dry_run:
        item.features = taste
        item.texture = texture if texture else {}
        item.richness = richness
        
        if not item.provenance:
            item.provenance = {}
        
        item.provenance["llm_taste_profile"] = taste
        item.provenance["llm_texture_profile"] = texture
        item.provenance["llm_richness"] = richness
        item.provenance["cuisine_typicality"] = cuisine_typicality
        item.provenance["feature_generation_method"] = "llm"
    
    return "llm_generated"


def extract_cached_llm_profile(item: MenuItem) -> Dict[str, float] | None:
    if not item.provenance:
        return None
    
    cached = item.provenance.get("llm_taste_profile")
    
    if not cached:
        return None
    
    if isinstance(cached, dict) and len(cached) > 0:
        return cached
    
    return None


def print_regeneration_stats(stats: Dict[str, int]) -> None:
    print("\n" + "="*60)
    print("REGENERATION STATISTICS")
    print("="*60)
    print(f"Total items:       {stats['total']}")
    print(f"LLM generated:     {stats['llm_generated']}")
    print(f"Cached (skipped):  {stats['cached']}")
    print(f"Failed:            {stats['failed']}")
    print(f"Skipped (no data): {stats['skipped']}")
    print("="*60)
    
    if stats['llm_generated'] > 0:
        cost_estimate = (stats['llm_generated'] / 200) * 0.04
        print(f"\nEstimated cost: ${cost_estimate:.4f}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Regenerate taste vectors for all menu items using LLM"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    
    args = parser.parse_args()
    
    try:
        stats = regenerate_all_taste_vectors_with_llm(dry_run=args.dry_run)
        print_regeneration_stats(stats)
        
        if args.dry_run:
            print("\nDRY RUN COMPLETED - No changes were made")
        else:
            print("\nREGENERATION COMPLETED SUCCESSFULLY")
    
    except LLMTasteVectorRegenerationError as e:
        print(f"\nError: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)
