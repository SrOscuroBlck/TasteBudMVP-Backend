from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime
from pathlib import Path
import json
import time

import numpy as np
import faiss

from config.settings import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class FAISSIndexMetadata:
    def __init__(
        self,
        dimension: int,
        count: int,
        item_ids: List[str],
        build_timestamp: str,
        version: str = "1.0"
    ):
        self.dimension = dimension
        self.count = count
        self.item_ids = item_ids
        self.build_timestamp = build_timestamp
        self.version = version

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "count": self.count,
            "item_ids": self.item_ids,
            "build_timestamp": self.build_timestamp,
            "version": self.version
        }

    @staticmethod
    def from_dict(data: dict) -> "FAISSIndexMetadata":
        return FAISSIndexMetadata(
            dimension=data["dimension"],
            count=data["count"],
            item_ids=data["item_ids"],
            build_timestamp=data["build_timestamp"],
            version=data.get("version", "1.0")
        )


class FAISSService:
    def __init__(self):
        self.index: Optional[faiss.Index] = None
        self.metadata: Optional[FAISSIndexMetadata] = None
        self._index_dir = Path(settings.FAISS_INDEX_PATH)
        self._index_dir.mkdir(parents=True, exist_ok=True)

    def build_index(
        self,
        embeddings: List[List[float]],
        item_ids: List[UUID],
        dimension: Optional[int] = None
    ) -> None:
        if not embeddings:
            raise ValueError("embeddings list cannot be empty for index building")

        if not item_ids:
            raise ValueError("item_ids list cannot be empty for index building")

        if len(embeddings) != len(item_ids):
            raise ValueError(
                f"embeddings and item_ids length mismatch: {len(embeddings)} vs {len(item_ids)}"
            )

        embeddings_array = np.array(embeddings, dtype=np.float32)
        
        if dimension is None:
            dimension = embeddings_array.shape[1]
        
        if embeddings_array.shape[1] != dimension:
            raise ValueError(
                f"embedding dimension mismatch: expected {dimension}, got {embeddings_array.shape[1]}"
            )

        logger.info(
            "Building FAISS index",
            extra={"count": len(embeddings), "dimension": dimension}
        )

        start_time = time.time()

        faiss.normalize_L2(embeddings_array)

        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(embeddings_array)

        build_duration = time.time() - start_time

        item_ids_str = [str(item_id) for item_id in item_ids]
        
        self.metadata = FAISSIndexMetadata(
            dimension=dimension,
            count=len(embeddings),
            item_ids=item_ids_str,
            build_timestamp=datetime.utcnow().isoformat()
        )

        logger.info(
            "FAISS index built successfully",
            extra={
                "count": self.metadata.count,
                "dimension": self.metadata.dimension,
                "build_duration_ms": round(build_duration * 1000, 2)
            }
        )

    def save(self, index_name: str = "default") -> None:
        if self.index is None:
            raise ValueError("cannot save index: no index has been built")

        if self.metadata is None:
            raise ValueError("cannot save index: metadata is missing")

        index_path = self._index_dir / f"{index_name}_{self.metadata.dimension}d.faiss"
        metadata_path = self._index_dir / f"{index_name}_{self.metadata.dimension}d.json"

        faiss.write_index(self.index, str(index_path))
        
        with open(metadata_path, "w") as f:
            json.dump(self.metadata.to_dict(), f, indent=2)

        logger.info(
            "FAISS index saved to disk",
            extra={
                "index_path": str(index_path),
                "metadata_path": str(metadata_path),
                "count": self.metadata.count
            }
        )

    def load(self, index_name: str = "default", dimension: int = 64) -> None:
        index_path = self._index_dir / f"{index_name}_{dimension}d.faiss"
        metadata_path = self._index_dir / f"{index_name}_{dimension}d.json"

        if not index_path.exists():
            raise FileNotFoundError(
                f"index file not found at {index_path}"
            )

        if not metadata_path.exists():
            raise FileNotFoundError(
                f"metadata file not found at {metadata_path}"
            )

        self.index = faiss.read_index(str(index_path))
        
        with open(metadata_path, "r") as f:
            metadata_dict = json.load(f)
            self.metadata = FAISSIndexMetadata.from_dict(metadata_dict)

        if self.metadata.dimension != dimension:
            raise ValueError(
                f"loaded index dimension mismatch: expected {dimension}, got {self.metadata.dimension}"
            )

        logger.info(
            "FAISS index loaded from disk",
            extra={
                "index_path": str(index_path),
                "count": self.metadata.count,
                "dimension": self.metadata.dimension
            }
        )

    def search(
        self,
        query_embedding: List[float],
        k: int = 20
    ) -> List[Tuple[UUID, float]]:
        if self.index is None:
            raise ValueError("cannot search: no index loaded or built")

        if self.metadata is None:
            raise ValueError("cannot search: metadata is missing")

        if query_embedding is None or len(query_embedding) == 0:
            raise ValueError("query_embedding cannot be empty")

        query_array = np.array([query_embedding], dtype=np.float32)

        if query_array.shape[1] != self.metadata.dimension:
            raise ValueError(
                f"query embedding dimension mismatch: expected {self.metadata.dimension}, got {query_array.shape[1]}"
            )

        faiss.normalize_L2(query_array)

        k_actual = min(k, self.metadata.count)

        start_time = time.time()
        distances, indices = self.index.search(query_array, k_actual)
        search_duration = time.time() - start_time

        results = []
        for idx, distance in zip(indices[0], distances[0]):
            if idx < len(self.metadata.item_ids):
                item_id = UUID(self.metadata.item_ids[idx])
                results.append((item_id, float(distance)))

        logger.info(
            "FAISS search completed",
            extra={
                "k_requested": k,
                "k_returned": len(results),
                "search_duration_ms": round(search_duration * 1000, 2)
            }
        )

        return results

    @property
    def is_loaded(self) -> bool:
        return self.index is not None and self.metadata is not None

    @property
    def index_size(self) -> int:
        if self.metadata is None:
            return 0
        return self.metadata.count
