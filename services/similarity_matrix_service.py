from typing import Dict, List, Tuple, Optional
from uuid import UUID
import numpy as np
import pickle
from pathlib import Path

from models import MenuItem
from models.user import TASTE_AXES
from utils.logger import setup_logger
from config.settings import settings

logger = setup_logger(__name__)


class SimilarityMatrixService:
    def __init__(self):
        self.matrix: Optional[np.ndarray] = None
        self.item_id_to_idx: Dict[UUID, int] = {}
        self.idx_to_item_id: Dict[int, UUID] = {}
        self.n_items: int = 0
        
    def build_matrix(self, items: List[MenuItem]) -> None:
        if not items:
            raise ValueError("items list cannot be empty for matrix building")
        
        n = len(items)
        self.n_items = n
        
        self.item_id_to_idx.clear()
        self.idx_to_item_id.clear()
        
        for idx, item in enumerate(items):
            self.item_id_to_idx[item.id] = idx
            self.idx_to_item_id[idx] = item.id
        
        feature_matrix = np.zeros((n, len(TASTE_AXES)))
        
        for idx, item in enumerate(items):
            for axis_idx, axis in enumerate(TASTE_AXES):
                feature_matrix[idx, axis_idx] = item.features.get(axis, 0.5)
        
        norms = np.linalg.norm(feature_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        feature_matrix_normalized = feature_matrix / norms
        
        self.matrix = feature_matrix_normalized @ feature_matrix_normalized.T
        
        memory_mb = self.matrix.nbytes / (1024 * 1024)
        
        logger.info(
            "Similarity matrix built successfully",
            extra={
                "n_items": n,
                "matrix_shape": self.matrix.shape,
                "memory_mb": round(memory_mb, 2),
                "taste_dimensions": len(TASTE_AXES)
            }
        )
    
    def get_similarity(self, item1_id: UUID, item2_id: UUID) -> float:
        if self.matrix is None:
            raise ValueError("Similarity matrix not built - call build_matrix first")
        
        idx1 = self.item_id_to_idx.get(item1_id)
        idx2 = self.item_id_to_idx.get(item2_id)
        
        if idx1 is None or idx2 is None:
            return 0.5
        
        return float(self.matrix[idx1, idx2])
    
    def get_top_similar(
        self,
        item_id: UUID,
        top_k: int = 10,
        exclude_self: bool = True
    ) -> List[Tuple[UUID, float]]:
        if self.matrix is None:
            raise ValueError("Similarity matrix not built - call build_matrix first")
        
        idx = self.item_id_to_idx.get(item_id)
        if idx is None:
            return []
        
        similarities = self.matrix[idx]
        
        if exclude_self:
            top_indices = np.argsort(similarities)[::-1][1:top_k+1]
        else:
            top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = [
            (self.idx_to_item_id[int(i)], float(similarities[i]))
            for i in top_indices
            if i in self.idx_to_item_id
        ]
        
        return results
    
    def get_batch_similarities(
        self,
        item_ids: List[UUID]
    ) -> Dict[Tuple[UUID, UUID], float]:
        if self.matrix is None:
            raise ValueError("Similarity matrix not built - call build_matrix first")
        
        results = {}
        
        for i, id1 in enumerate(item_ids):
            for id2 in item_ids[i+1:]:
                similarity = self.get_similarity(id1, id2)
                results[(id1, id2)] = similarity
                results[(id2, id1)] = similarity
        
        return results
    
    def save_to_disk(self, path: Optional[str] = None) -> None:
        if self.matrix is None:
            raise ValueError("Cannot save - matrix not built")
        
        if path is None:
            path = settings.FAISS_INDEX_PATH + "similarity_matrix.pkl"
        
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "matrix": self.matrix,
            "item_id_to_idx": self.item_id_to_idx,
            "idx_to_item_id": self.idx_to_item_id,
            "n_items": self.n_items
        }
        
        with open(path, "wb") as f:
            pickle.dump(data, f)
        
        logger.info(
            "Similarity matrix saved to disk",
            extra={"path": path, "n_items": self.n_items}
        )
    
    def load_from_disk(self, path: Optional[str] = None) -> None:
        if path is None:
            path = settings.FAISS_INDEX_PATH + "similarity_matrix.pkl"
        
        if not Path(path).exists():
            raise FileNotFoundError(f"Similarity matrix file not found at {path}")
        
        with open(path, "rb") as f:
            data = pickle.load(f)
        
        self.matrix = data["matrix"]
        self.item_id_to_idx = data["item_id_to_idx"]
        self.idx_to_item_id = data["idx_to_item_id"]
        self.n_items = data.get("n_items", len(self.idx_to_item_id))
        
        logger.info(
            "Similarity matrix loaded from disk",
            extra={"path": path, "n_items": self.n_items}
        )
    
    def is_built(self) -> bool:
        return self.matrix is not None


_global_similarity_service: Optional[SimilarityMatrixService] = None


def get_similarity_service() -> SimilarityMatrixService:
    global _global_similarity_service
    
    if _global_similarity_service is None:
        _global_similarity_service = SimilarityMatrixService()
    
    return _global_similarity_service
