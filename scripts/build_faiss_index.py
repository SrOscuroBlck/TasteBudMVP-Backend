#!/usr/bin/env python
"""
Build FAISS index from MenuItems with embeddings in the database.
Run this script after seeding data or generating embeddings.
"""
import sys
from pathlib import Path
import os
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select

from config.database import engine
from models.restaurant import MenuItem
from services.faiss_service import FAISSService
from utils.logger import setup_logger

logger = setup_logger(__name__)


def build_faiss_index(dimension: int = 64, index_name: str = "current"):
    start_time = time.time()
    
    with Session(engine) as session:
        if dimension == 64:
            items = session.exec(
                select(MenuItem)
                .where(MenuItem.reduced_embedding.is_not(None))
            ).all()
            embedding_field = "reduced_embedding"
        elif dimension == 1536:
            items = session.exec(
                select(MenuItem)
                .where(MenuItem.embedding.is_not(None))
            ).all()
            embedding_field = "embedding"
        else:
            raise ValueError(f"unsupported dimension: {dimension}. Use 64 or 1536")
        
        if not items:
            logger.warning(
                f"No items found with {embedding_field}",
                extra={"dimension": dimension}
            )
            print(f"\n[ERROR] No MenuItems with {embedding_field} found in database")
            print("[INFO] Run scripts/generate_embeddings.py first to generate embeddings\n")
            return
        
        print(f"\n[INFO] Loading MenuItems with embeddings...")
        print(f"[INFO] Found {len(items):,} items with embeddings")
        print(f"[INFO] Using {embedding_field} ({dimension} dimensions)")
        
        logger.info(
            "Building FAISS index from database",
            extra={
                "item_count": len(items),
                "dimension": dimension,
                "embedding_field": embedding_field
            }
        )
        
        embeddings = []
        item_ids = []
        
        for item in items:
            if dimension == 64 and item.reduced_embedding is not None:
                embeddings.append(item.reduced_embedding)
                item_ids.append(item.id)
            elif dimension == 1536 and item.embedding is not None:
                embeddings.append(item.embedding)
                item_ids.append(item.id)
        
        if not embeddings:
            logger.error("No valid embeddings extracted from items")
            print("\n[ERROR] No valid embeddings extracted from items\n")
            return
        
        print(f"[INFO] Building FAISS index...")
        
        service = FAISSService()
        service.build_index(
            embeddings=embeddings,
            item_ids=item_ids,
            dimension=dimension
        )
        
        print(f"[INFO] Index built successfully")
        print(f"[INFO] Saving index to data/faiss_indexes/{index_name}_{dimension}d.faiss")
        
        service.save(index_name)
        
        print(f"[INFO] Index saved successfully")
        
        logger.info(
            "FAISS index built and saved successfully",
            extra={
                "index_name": index_name,
                "dimension": dimension,
                "count": service.metadata.count,
                "build_timestamp": service.metadata.build_timestamp
            }
        )
        
        build_duration = time.time() - start_time
        
        index_path = Path(f"data/faiss_indexes/{index_name}_{dimension}d.faiss")
        metadata_path = Path(f"data/faiss_indexes/{index_name}_{dimension}d.json")
        
        index_size = 0
        if index_path.exists():
            index_size = os.path.getsize(index_path)
        
        test_query = embeddings[0]
        results = service.search(test_query, k=5)
        
        print(f"\nBuild Statistics:")
        print(f"  - Items indexed: {service.metadata.count:,}")
        print(f"  - Embedding dimension: {dimension}")
        print(f"  - Build time: {build_duration:.2f}s")
        print(f"  - Index size: {index_size / 1024:.0f} KB")
        print(f"  - Index type: IndexFlatIP")
        print(f"  - Metric: cosine")
        print(f"  - Test query: {len(results)} results")
        print(f"  - Top match: {results[0][0]} (similarity: {results[0][1]:.4f})\n")


if __name__ == "__main__":
    dimension = 64
    index_name = "current"
    
    if len(sys.argv) > 1:
        try:
            dimension = int(sys.argv[1])
        except ValueError:
            print(f"Invalid dimension: {sys.argv[1]}")
            print("Usage: python scripts/build_faiss_index.py [dimension] [index_name]")
            print("  dimension: 64 (default) or 1536")
            print("  index_name: current (default) or custom name")
            sys.exit(1)
    
    if len(sys.argv) > 2:
        index_name = sys.argv[2]
    
    build_faiss_index(dimension=dimension, index_name=index_name)
