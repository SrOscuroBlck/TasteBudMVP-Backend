from sqlmodel import Session, select
import sys

from config.database import engine
from models.restaurant import MenuItem
from services.faiss_service import FAISSService
from utils.logger import setup_logger

logger = setup_logger(__name__)


def build_faiss_index(dimension: int = 64, index_name: str = "default"):
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
            print(f"No MenuItems with {embedding_field} found in database")
            print("Run scripts/generate_embeddings.py first to generate embeddings")
            return
        
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
            if dimension == 64 and item.reduced_embedding:
                embeddings.append(item.reduced_embedding)
                item_ids.append(item.id)
            elif dimension == 1536 and item.embedding:
                embeddings.append(item.embedding)
                item_ids.append(item.id)
        
        if not embeddings:
            logger.error("No valid embeddings extracted from items")
            return
        
        service = FAISSService()
        service.build_index(
            embeddings=embeddings,
            item_ids=item_ids,
            dimension=dimension
        )
        
        service.save(index_name)
        
        logger.info(
            "FAISS index built and saved successfully",
            extra={
                "index_name": index_name,
                "dimension": dimension,
                "count": service.metadata.count,
                "build_timestamp": service.metadata.build_timestamp
            }
        )
        
        print(f"✓ FAISS index built successfully")
        print(f"  Name: {index_name}")
        print(f"  Dimension: {dimension}D")
        print(f"  Items: {service.metadata.count}")
        print(f"  Path: data/faiss_indexes/{index_name}_{dimension}d.faiss")
        
        test_query = embeddings[0]
        results = service.search(test_query, k=5)
        
        print(f"  Test query returned {len(results)} results")
        print(f"  Top result: {results[0][0]} (similarity: {results[0][1]:.4f})")


if __name__ == "__main__":
    dimension = 64
    index_name = "default"
    
    if len(sys.argv) > 1:
        try:
            dimension = int(sys.argv[1])
        except ValueError:
            print(f"Invalid dimension: {sys.argv[1]}")
            print("Usage: python build_faiss_index.py [dimension] [index_name]")
            print("  dimension: 64 (default) or 1536")
            print("  index_name: default (default) or custom name")
            sys.exit(1)
    
    if len(sys.argv) > 2:
        index_name = sys.argv[2]
    
    print(f"Building FAISS index with {dimension}D embeddings...")
    build_faiss_index(dimension=dimension, index_name=index_name)
