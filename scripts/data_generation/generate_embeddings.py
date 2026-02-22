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
from services.features.embedding_service import EmbeddingService
from services.ml.umap_reducer import UMAPReducer
from utils.logger import setup_logger

logger = setup_logger(__name__)


def generate_embeddings_for_all_items():
    embedding_service = EmbeddingService()
    
    with Session(engine) as session:
        statement = select(MenuItem).where(MenuItem.embedding == None)
        items = session.exec(statement).all()
        
        if not items:
            logger.info("All items already have embeddings")
            return
        
        logger.info("Starting embedding generation", extra={"item_count": len(items)})
        
        # Convert all items to dict format for batch processing
        items_dicts = []
        for item in items:
            items_dicts.append({
                "name": item.name,
                "description": item.description,
                "ingredients": item.ingredients,
                "cuisine": item.cuisine,
                "cooking_method": item.cooking_method,
                "dietary_tags": item.dietary_tags,
                "course": item.course,
                "spice_level": item.spice_level,
            })
        
        # Generate embeddings in batches (default batch_size=100)
        results = embedding_service.generate_batch(items_dicts)
        
        # Apply results to items
        success_count = 0
        for item, result in zip(items, results):
            if result:
                item.embedding = result["embedding"]
                item.embedding_model = result["embedding_model"]
                item.embedding_version = result["embedding_version"]
                item.last_embedded_at = result["last_embedded_at"]
                session.add(item)
                success_count += 1
            else:
                logger.error("Failed to generate embedding", extra={"item_id": str(item.id), "item_name": item.name})
        
        session.commit()
        logger.info("Completed embedding generation", extra={"item_count": len(items), "success_count": success_count})


def reduce_embeddings_for_all_items():
    with Session(engine) as session:
        statement = select(MenuItem).where(
            MenuItem.embedding != None,
            MenuItem.reduced_embedding == None
        )
        items = session.exec(statement).all()
        
        if not items:
            logger.info("All items already have reduced embeddings")
            return
        
        logger.info("Starting UMAP dimensionality reduction", extra={"item_count": len(items)})
        
        # Filter out any items that somehow have a None embedding; UMAP expects a List[List[float]]
        filtered = [(item, item.embedding) for item in items if item.embedding is not None]
        embeddings = [e for (_item, e) in filtered]

        reducer = UMAPReducer(n_components=64)

        if len(embeddings) < 64:
            logger.warning("Insufficient items for UMAP reduction, skipping", extra={"item_count": len(embeddings), "minimum_required": 64})
            return
        reduced = reducer.fit_transform(embeddings)

        reducer.save("data/umap_reducer.joblib")
        logger.info("Saved UMAP reducer model", extra={"path": "data/umap_reducer.joblib"})

        # Map reduced embeddings back to the original items that had embeddings
        for (item, _orig_embedding), reduced_embedding in zip(filtered, reduced):
            item.reduced_embedding = reduced_embedding
            session.add(item)
        
        session.commit()
        logger.info("Completed dimensionality reduction", extra={"item_count": len(items)})


def main():
    logger.info("Starting embedding generation pipeline")
    
    generate_embeddings_for_all_items()
    
    reduce_embeddings_for_all_items()
    
    logger.info("Embedding generation pipeline complete")


if __name__ == "__main__":
    main()
