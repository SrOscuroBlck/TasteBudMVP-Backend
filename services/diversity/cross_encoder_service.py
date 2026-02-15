from typing import List, Tuple, Optional
import time

from models import MenuItem
from models.query import ParsedQuery
from utils.logger import setup_logger

logger = setup_logger(__name__)


class CrossEncoderService:
    
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None
        self._model_loaded = False
    
    def _load_model(self) -> bool:
        if self._model_loaded:
            return True
        
        try:
            from sentence_transformers import CrossEncoder
            
            logger.info(
                "Loading cross-encoder model",
                extra={"model_name": self.model_name}
            )
            
            self._model = CrossEncoder(self.model_name)
            self._model_loaded = True
            
            logger.info("Cross-encoder model loaded successfully")
            return True
            
        except ImportError as e:
            logger.warning(
                "sentence-transformers not available, cross-encoder disabled",
                extra={"error": str(e)}
            )
            return False
        except Exception as e:
            logger.error(
                "Failed to load cross-encoder model",
                extra={"error": str(e)},
                exc_info=True
            )
            return False
    
    def rerank_query_results(
        self,
        query: str,
        candidates: List[MenuItem],
        top_k: Optional[int] = None
    ) -> List[Tuple[MenuItem, float]]:
        if not candidates:
            return []
        
        if not self._load_model():
            logger.warning("Cross-encoder not available, returning candidates as-is")
            return [(item, 0.0) for item in candidates]
        
        logger.info(
            "Reranking with cross-encoder",
            extra={
                "query": query,
                "candidate_count": len(candidates),
                "top_k": top_k
            }
        )
        
        start_time = time.time()
        
        pairs = self._build_query_item_pairs(query, candidates)
        
        scores = self._model.predict(pairs)
        
        scored_items = list(zip(candidates, scores))
        scored_items.sort(key=lambda x: x[1], reverse=True)
        
        inference_time = time.time() - start_time
        
        logger.info(
            "Cross-encoder reranking completed",
            extra={
                "candidate_count": len(candidates),
                "inference_time_ms": round(inference_time * 1000, 2),
                "top_score": float(scored_items[0][1]) if scored_items else 0.0
            }
        )
        
        if top_k:
            return scored_items[:top_k]
        
        return scored_items
    
    def rerank_parsed_query_results(
        self,
        parsed_query: ParsedQuery,
        candidates: List[MenuItem],
        top_k: Optional[int] = None
    ) -> List[Tuple[MenuItem, float]]:
        query_text = parsed_query.embedding_text
        return self.rerank_query_results(query_text, candidates, top_k)
    
    def _build_query_item_pairs(
        self,
        query: str,
        candidates: List[MenuItem]
    ) -> List[Tuple[str, str]]:
        pairs = []
        
        for item in candidates:
            item_text = self._build_item_text(item)
            pairs.append((query, item_text))
        
        return pairs
    
    def _build_item_text(self, item: MenuItem) -> str:
        parts = [item.name]
        
        if item.description:
            parts.append(item.description)
        
        if item.cuisine:
            parts.append(f"Cuisine: {', '.join(item.cuisine)}")
        
        if item.ingredients:
            parts.append(f"Ingredients: {', '.join(item.ingredients[:5])}")
        
        if item.course:
            parts.append(f"Course: {item.course}")
        
        return ". ".join(parts)
    
    @property
    def is_available(self) -> bool:
        return self._load_model()
    
    def benchmark_latency(self, num_candidates: int = 30) -> Optional[float]:
        if not self._load_model():
            return None
        
        dummy_query = "something spicy and savory"
        dummy_items = [
            MenuItem(
                name=f"Test Item {i}",
                description="A delicious test dish with various flavors",
                cuisine=["Test"],
                ingredients=["ingredient1", "ingredient2"],
                course="main"
            )
            for i in range(num_candidates)
        ]
        
        start_time = time.time()
        self.rerank_query_results(dummy_query, dummy_items)
        latency = time.time() - start_time
        
        logger.info(
            "Cross-encoder latency benchmark",
            extra={
                "num_candidates": num_candidates,
                "latency_ms": round(latency * 1000, 2)
            }
        )
        
        return latency
