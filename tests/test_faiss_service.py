from uuid import uuid4, UUID
from pathlib import Path
import shutil
import time
import numpy as np
import pytest

from services.faiss_service import FAISSService, FAISSIndexMetadata


class TestFAISSIndexMetadata:
    def test_metadata_creation(self):
        item_ids = [str(uuid4()) for _ in range(10)]
        metadata = FAISSIndexMetadata(
            dimension=64,
            count=10,
            item_ids=item_ids,
            build_timestamp="2026-01-04T00:00:00"
        )
        
        assert metadata.dimension == 64
        assert metadata.count == 10
        assert len(metadata.item_ids) == 10
        assert metadata.version == "1.0"

    def test_metadata_to_dict(self):
        item_ids = [str(uuid4()) for _ in range(5)]
        metadata = FAISSIndexMetadata(
            dimension=64,
            count=5,
            item_ids=item_ids,
            build_timestamp="2026-01-04T00:00:00"
        )
        
        data = metadata.to_dict()
        assert data["dimension"] == 64
        assert data["count"] == 5
        assert len(data["item_ids"]) == 5
        assert "build_timestamp" in data

    def test_metadata_from_dict(self):
        data = {
            "dimension": 128,
            "count": 20,
            "item_ids": [str(uuid4()) for _ in range(20)],
            "build_timestamp": "2026-01-04T00:00:00",
            "version": "1.0"
        }
        
        metadata = FAISSIndexMetadata.from_dict(data)
        assert metadata.dimension == 128
        assert metadata.count == 20
        assert len(metadata.item_ids) == 20


class TestFAISSService:
    @pytest.fixture
    def service(self):
        svc = FAISSService()
        yield svc
        test_index_dir = Path("data/faiss_indexes")
        if test_index_dir.exists():
            for file in test_index_dir.glob("test_*.faiss"):
                file.unlink()
            for file in test_index_dir.glob("test_*.json"):
                file.unlink()

    @pytest.fixture
    def sample_embeddings_64d(self):
        np.random.seed(42)
        embeddings = []
        for i in range(50):
            embedding = np.random.randn(64).astype(np.float32)
            embedding = embedding / np.linalg.norm(embedding)
            embeddings.append(embedding.tolist())
        return embeddings

    @pytest.fixture
    def sample_embeddings_1536d(self):
        np.random.seed(42)
        embeddings = []
        for i in range(20):
            embedding = np.random.randn(1536).astype(np.float32)
            embedding = embedding / np.linalg.norm(embedding)
            embeddings.append(embedding.tolist())
        return embeddings

    @pytest.fixture
    def sample_item_ids(self):
        return [uuid4() for _ in range(50)]

    def test_service_initialization(self, service):
        assert service.index is None
        assert service.metadata is None
        assert not service.is_loaded
        assert service.index_size == 0

    def test_build_index_with_valid_embeddings(self, service, sample_embeddings_64d, sample_item_ids):
        service.build_index(
            embeddings=sample_embeddings_64d,
            item_ids=sample_item_ids,
            dimension=64
        )
        
        assert service.index is not None
        assert service.metadata is not None
        assert service.metadata.dimension == 64
        assert service.metadata.count == 50
        assert service.is_loaded
        assert service.index_size == 50

    def test_build_index_with_empty_embeddings(self, service):
        with pytest.raises(ValueError) as exc_info:
            service.build_index(embeddings=[], item_ids=[])
        
        assert "embeddings list cannot be empty" in str(exc_info.value)

    def test_build_index_with_empty_item_ids(self, service, sample_embeddings_64d):
        with pytest.raises(ValueError) as exc_info:
            service.build_index(embeddings=sample_embeddings_64d, item_ids=[])
        
        assert "item_ids list cannot be empty" in str(exc_info.value)

    def test_build_index_with_length_mismatch(self, service, sample_embeddings_64d, sample_item_ids):
        with pytest.raises(ValueError) as exc_info:
            service.build_index(
                embeddings=sample_embeddings_64d[:10],
                item_ids=sample_item_ids
            )
        
        assert "length mismatch" in str(exc_info.value)

    def test_build_index_with_dimension_mismatch(self, service, sample_embeddings_64d, sample_item_ids):
        with pytest.raises(ValueError) as exc_info:
            service.build_index(
                embeddings=sample_embeddings_64d,
                item_ids=sample_item_ids,
                dimension=128
            )
        
        assert "dimension mismatch" in str(exc_info.value)

    def test_build_index_infers_dimension(self, service, sample_embeddings_1536d):
        item_ids = [uuid4() for _ in range(20)]
        service.build_index(
            embeddings=sample_embeddings_1536d,
            item_ids=item_ids
        )
        
        assert service.metadata.dimension == 1536

    def test_save_without_built_index(self, service):
        with pytest.raises(ValueError) as exc_info:
            service.save("test_empty")
        
        assert "no index has been built" in str(exc_info.value)

    def test_save_and_load_round_trip(self, service, sample_embeddings_64d, sample_item_ids):
        service.build_index(
            embeddings=sample_embeddings_64d,
            item_ids=sample_item_ids,
            dimension=64
        )
        
        original_count = service.metadata.count
        original_item_ids = service.metadata.item_ids.copy()
        
        service.save("test_roundtrip")
        
        new_service = FAISSService()
        new_service.load("test_roundtrip", dimension=64)
        
        assert new_service.is_loaded
        assert new_service.metadata.count == original_count
        assert new_service.metadata.dimension == 64
        assert new_service.metadata.item_ids == original_item_ids

    def test_load_nonexistent_index(self, service):
        with pytest.raises(FileNotFoundError) as exc_info:
            service.load("nonexistent_index", dimension=64)
        
        assert "index file not found" in str(exc_info.value)

    def test_load_with_wrong_dimension(self, service, sample_embeddings_64d, sample_item_ids):
        service.build_index(
            embeddings=sample_embeddings_64d,
            item_ids=sample_item_ids,
            dimension=64
        )
        service.save("test_dimension")
        
        new_service = FAISSService()
        import shutil
        from pathlib import Path
        
        test_64d_path = Path("data/faiss_indexes/test_dimension_64d.faiss")
        test_128d_path = Path("data/faiss_indexes/test_dimension_128d.faiss")
        shutil.copy(test_64d_path, test_128d_path)
        
        test_64d_meta = Path("data/faiss_indexes/test_dimension_64d.json")
        test_128d_meta = Path("data/faiss_indexes/test_dimension_128d.json")
        shutil.copy(test_64d_meta, test_128d_meta)
        
        with pytest.raises(ValueError) as exc_info:
            new_service.load("test_dimension", dimension=128)
        
        assert "dimension mismatch" in str(exc_info.value)
        
        test_128d_path.unlink()
        test_128d_meta.unlink()

    def test_search_returns_nearest_neighbors(self, service, sample_embeddings_64d, sample_item_ids):
        service.build_index(
            embeddings=sample_embeddings_64d,
            item_ids=sample_item_ids,
            dimension=64
        )
        
        query_embedding = sample_embeddings_64d[0]
        results = service.search(query_embedding, k=5)
        
        assert len(results) == 5
        assert all(isinstance(item_id, UUID) for item_id, _ in results)
        assert all(isinstance(distance, float) for _, distance in results)
        
        assert results[0][0] == sample_item_ids[0]

    def test_search_with_k_larger_than_index(self, service, sample_embeddings_64d, sample_item_ids):
        small_embeddings = sample_embeddings_64d[:10]
        small_ids = sample_item_ids[:10]
        
        service.build_index(
            embeddings=small_embeddings,
            item_ids=small_ids,
            dimension=64
        )
        
        query_embedding = small_embeddings[0]
        results = service.search(query_embedding, k=100)
        
        assert len(results) == 10

    def test_search_without_index(self, service, sample_embeddings_64d):
        with pytest.raises(ValueError) as exc_info:
            service.search(sample_embeddings_64d[0], k=5)
        
        assert "no index loaded or built" in str(exc_info.value)

    def test_search_with_empty_embedding(self, service, sample_embeddings_64d, sample_item_ids):
        service.build_index(
            embeddings=sample_embeddings_64d,
            item_ids=sample_item_ids,
            dimension=64
        )
        
        with pytest.raises(ValueError) as exc_info:
            service.search([], k=5)
        
        assert "query_embedding cannot be empty" in str(exc_info.value)

    def test_search_with_wrong_dimension(self, service, sample_embeddings_64d, sample_item_ids):
        service.build_index(
            embeddings=sample_embeddings_64d,
            item_ids=sample_item_ids,
            dimension=64
        )
        
        wrong_dimension_embedding = [0.1] * 128
        
        with pytest.raises(ValueError) as exc_info:
            service.search(wrong_dimension_embedding, k=5)
        
        assert "dimension mismatch" in str(exc_info.value)

    def test_search_returns_sorted_by_similarity(self, service, sample_embeddings_64d, sample_item_ids):
        service.build_index(
            embeddings=sample_embeddings_64d,
            item_ids=sample_item_ids,
            dimension=64
        )
        
        query_embedding = sample_embeddings_64d[0]
        results = service.search(query_embedding, k=10)
        
        distances = [distance for _, distance in results]
        assert distances == sorted(distances, reverse=True)

    def test_performance_10k_items_64d(self, service):
        np.random.seed(42)
        embeddings = []
        for i in range(10000):
            embedding = np.random.randn(64).astype(np.float32)
            embedding = embedding / np.linalg.norm(embedding)
            embeddings.append(embedding.tolist())
        
        item_ids = [uuid4() for _ in range(10000)]
        
        build_start = time.time()
        service.build_index(embeddings=embeddings, item_ids=item_ids, dimension=64)
        build_duration = (time.time() - build_start) * 1000
        
        assert build_duration < 1000
        
        query_embedding = embeddings[0]
        
        search_times = []
        for _ in range(10):
            search_start = time.time()
            results = service.search(query_embedding, k=20)
            search_duration = (time.time() - search_start) * 1000
            search_times.append(search_duration)
        
        avg_search_time = sum(search_times) / len(search_times)
        assert avg_search_time < 50

    def test_performance_1536d_embeddings(self, service):
        np.random.seed(42)
        embeddings = []
        for i in range(1000):
            embedding = np.random.randn(1536).astype(np.float32)
            embedding = embedding / np.linalg.norm(embedding)
            embeddings.append(embedding.tolist())
        
        item_ids = [uuid4() for _ in range(1000)]
        
        service.build_index(embeddings=embeddings, item_ids=item_ids, dimension=1536)
        
        query_embedding = embeddings[0]
        
        search_start = time.time()
        results = service.search(query_embedding, k=20)
        search_duration = (time.time() - search_start) * 1000
        
        assert search_duration < 200

    def test_multiple_searches_consistent_results(self, service, sample_embeddings_64d, sample_item_ids):
        service.build_index(
            embeddings=sample_embeddings_64d,
            item_ids=sample_item_ids,
            dimension=64
        )
        
        query_embedding = sample_embeddings_64d[5]
        
        results1 = service.search(query_embedding, k=10)
        results2 = service.search(query_embedding, k=10)
        
        assert results1 == results2

    def test_save_load_preserves_search_results(self, service, sample_embeddings_64d, sample_item_ids):
        service.build_index(
            embeddings=sample_embeddings_64d,
            item_ids=sample_item_ids,
            dimension=64
        )
        
        query_embedding = sample_embeddings_64d[10]
        results_before = service.search(query_embedding, k=5)
        
        service.save("test_preserve")
        
        new_service = FAISSService()
        new_service.load("test_preserve", dimension=64)
        results_after = new_service.search(query_embedding, k=5)
        
        assert results_before == results_after
