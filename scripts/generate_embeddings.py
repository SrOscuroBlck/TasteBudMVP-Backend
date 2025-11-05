#!/usr/bin/env python
"""
Generate embeddings for all menu items in the database.
Run this script after seeding data or when adding new items in bulk.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select
from config.database import engine
from models.restaurant import MenuItem
from services.embedding_service import EmbeddingService
from services.umap_reducer import UMAPReducer


def generate_embeddings_for_all_items():
    embedding_service = EmbeddingService()
    
    with Session(engine) as session:
        statement = select(MenuItem).where(MenuItem.embedding == None)
        items = session.exec(statement).all()
        
        if not items:
            print("✓ All items already have embeddings")
            return
        
        print(f"Generating embeddings for {len(items)} items...")
        
        for i, item in enumerate(items, 1):
            # Convert to dict
            item_dict = {
                "name": item.name,
                "description": item.description,
                "ingredients": item.ingredients,
                "cuisine": item.cuisine,
                "cooking_method": item.cooking_method,
                "dietary_tags": item.dietary_tags,
                "course": item.course,
                "spice_level": item.spice_level,
            }
            
            result = embedding_service.generate_embedding(item_dict)
            
            if result:
                item.embedding = result["embedding"]
                item.embedding_model = result["embedding_model"]
                item.embedding_version = result["embedding_version"]
                item.last_embedded_at = result["last_embedded_at"]
                session.add(item)
                print(f"  [{i}/{len(items)}] ✓ {item.name}")
            else:
                print(f"  [{i}/{len(items)}] ✗ Failed: {item.name}")
        
        session.commit()
        print(f"\n✓ Generated embeddings for {len(items)} items")


def reduce_embeddings_for_all_items():
    with Session(engine) as session:
        statement = select(MenuItem).where(
            MenuItem.embedding != None,
            MenuItem.reduced_embedding == None
        )
        items = session.exec(statement).all()
        
        if not items:
            print("✓ All items already have reduced embeddings")
            return
        
        print(f"\nReducing embeddings for {len(items)} items using UMAP...")
        
        # Filter out any items that somehow have a None embedding; UMAP expects a List[List[float]]
        filtered = [(item, item.embedding) for item in items if item.embedding is not None]
        embeddings = [e for (_item, e) in filtered]

        reducer = UMAPReducer(n_components=64)

        if len(embeddings) < 64:
            print(f"  ⚠ Only {len(embeddings)} items. UMAP works best with more data.")
            print("  Skipping dimensionality reduction for now.")
            print("  Will use full embeddings for FAISS.")
            return
        reduced = reducer.fit_transform(embeddings)

        reducer.save("data/umap_reducer.joblib")
        print("  ✓ Saved UMAP reducer to data/umap_reducer.joblib")

        # Map reduced embeddings back to the original items that had embeddings
        for (item, _orig_embedding), reduced_embedding in zip(filtered, reduced):
            item.reduced_embedding = reduced_embedding
            session.add(item)
        
        session.commit()
        print(f"✓ Reduced embeddings for {len(items)} items")


def main():
    print("=" * 60)
    print("EMBEDDING GENERATION PIPELINE")
    print("=" * 60)
    
    generate_embeddings_for_all_items()
    
    reduce_embeddings_for_all_items()
    
    print("\n" + "=" * 60)
    print("COMPLETE")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Build FAISS index: python scripts/build_faiss_index.py")
    print("  2. Test recommendations with new embeddings")


if __name__ == "__main__":
    main()
