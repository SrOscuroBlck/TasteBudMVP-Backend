from datetime import datetime
from sqlmodel import Session, select
import numpy as np
import time

from config.database import engine
from models.restaurant import MenuItem
from services.faiss_service import FAISSService


def test_faiss_integration_with_real_menu_items():
    with Session(engine) as session:
        items_with_embeddings = session.exec(
            select(MenuItem)
            .where(MenuItem.reduced_embedding.is_not(None))
        ).all()
        
        if len(items_with_embeddings) < 10:
            print(f"Skipping integration test: only {len(items_with_embeddings)} items with embeddings found")
            print("Run scripts/generate_embeddings.py first to generate embeddings")
            return
        
        print(f"Testing FAISS with {len(items_with_embeddings)} real MenuItems")
        
        embeddings = []
        item_ids = []
        
        for item in items_with_embeddings:
            if item.reduced_embedding:
                embeddings.append(item.reduced_embedding)
                item_ids.append(item.id)
        
        service = FAISSService()
        
        build_start = time.time()
        service.build_index(embeddings=embeddings, item_ids=item_ids, dimension=64)
        build_duration = (time.time() - build_start) * 1000
        
        print(f"Built index in {build_duration:.2f}ms")
        
        service.save("integration_test")
        
        query_item = items_with_embeddings[0]
        query_embedding = query_item.reduced_embedding
        
        search_start = time.time()
        results = service.search(query_embedding, k=10)
        search_duration = (time.time() - search_start) * 1000
        
        print(f"Search completed in {search_duration:.2f}ms")
        print(f"Query item: {query_item.name}")
        print(f"Top 5 similar items:")
        
        for i, (item_id, distance) in enumerate(results[:5]):
            similar_item = session.get(MenuItem, item_id)
            if similar_item:
                print(f"  {i+1}. {similar_item.name} (similarity: {distance:.4f})")
        
        assert len(results) == 10
        assert results[0][0] == query_item.id
        assert search_duration < 100
        
        new_service = FAISSService()
        new_service.load("integration_test", dimension=64)
        
        results_after_load = new_service.search(query_embedding, k=10)
        assert results == results_after_load
        
        print("✓ Integration test passed")


if __name__ == "__main__":
    test_faiss_integration_with_real_menu_items()
