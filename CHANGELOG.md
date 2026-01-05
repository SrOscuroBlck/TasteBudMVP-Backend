# Changelog

All notable changes to the TasteBud recommendation system.

## [Phase 1.2] - 2026-01-04

### Added - Fast Similarity Search with FAISS

#### FAISSService
- **FAISSService** (`services/faiss_service.py`)
  - Fast k-nearest neighbor search using FAISS IndexFlatIP
  - Build index from embeddings with automatic vector normalization
  - Persistent storage to `data/faiss_indexes/` directory
  - Support for both 64D (reduced) and 1536D (full) embeddings
  - Index metadata tracking (dimension, count, build timestamp, version)
  - UUID mapping for MenuItem ID preservation
  - Fail-fast validation with clear error messages
  
#### Performance Characteristics
- **Build Time**: <1 second for 10K items
- **Query Time**: 
  - 64D embeddings: <5ms average for 10K items
  - 1536D embeddings: <20ms average for 1K items
- **Accuracy**: Exact search with normalized vectors for cosine similarity
- **Memory**: Efficient in-memory index with disk persistence

#### Testing
- Comprehensive unit test suite (`tests/test_faiss_service.py`)
  - 24 test cases covering happy path and edge cases
  - Build, save/load, search functionality
  - Error handling (empty embeddings, dimension mismatch, missing files)
  - Performance benchmarks for 10K and 100K item datasets
- Integration test with real MenuItem data (`tests/test_faiss_integration.py`)
  - End-to-end validation with database queries
  - Round-trip save/load verification
  - Similarity search accuracy validation

#### Configuration
- Added `FAISS_INDEX_PATH` setting to `config/settings.py`
  - Default: `data/faiss_indexes/`
  - Configurable via environment variable

#### Scripts
- **build_faiss_index.py** - Build FAISS index from database embeddings
  - Support for both 64D and 1536D embeddings
  - Configurable index naming
  - Automatic validation with test query
  - Usage: `python scripts/build_faiss_index.py [dimension] [index_name]`

---

## [Phase 1.1.1] - 2026-01-04

### Changed

#### LLM Configuration
- **Updated to GPT-5 nano** as primary model
  - Model: `gpt-5-nano`
  - Pricing: $0.05 input / $0.40 output per 1M tokens
  - 400K context window, 128K max output tokens
  - Fastest and most cost-efficient GPT-5 variant
  - Excellent for summarization and classification tasks
- **Fallback to GPT-4.1 nano** when GPT-5 unavailable
  - Model: `gpt-4.1-nano`
  - Pricing: $0.10 input / $0.40 output per 1M tokens
  - 1M token context window, strong instruction following
- Replaced deprecated GPT-4o-mini references across all configuration files

---

## [Phase 1.1] - 2025-11-05

### Added - Infrastructure & Foundation

#### Docker & Database
- PostgreSQL 16 with pgvector 0.5.1 extension for vector similarity search
- Redis 7 for caching layer (prepared for Phase 5)
- Docker Compose orchestration with health checks for all services
- API container with FastAPI and auto-reload
- Database auto-sync with SQLModel (no Alembic per project requirements)

#### Vector Embeddings System
- **EmbeddingService** (`services/embedding_service.py`)
  - OpenAI text-embedding-3-small (1536 dimensions) as primary
  - sentence-transformers all-MiniLM-L6-v2 as local fallback
  - Rich text generation from MenuItem fields
  - True batch processing (single API call per batch, not N calls)
  - Automatic dimension normalization and padding

#### Dimensionality Reduction
- **UMAPReducer** (`services/umap_reducer.py`)
  - Reduces 1536 dims → 64 dims for FAISS efficiency
  - Cosine metric for similarity preservation
  - Model persistence with joblib
  - Automatic skip for datasets <64 items

#### Scripts & Pipeline
- **generate_embeddings.py** - Batch embed all MenuItems without embeddings
  - Batch processing with configurable batch size (default 100)
  - UMAP reduction when sufficient data available
  - Structured logging with correlation tracking
  - Progress reporting and error handling

#### Database Schema
- Added vector columns to `MenuItem` model:
  - `embedding` (Vector 1536) - Full embedding
  - `reduced_embedding` (Vector 64) - UMAP-reduced
  - `embedding_model` - Model identifier
  - `embedding_version` - Schema version
  - `last_embedded_at` - Timestamp
- pgvector extension auto-enabled on startup via lifespan hook

#### API Enhancements
- `GET /api/v1/restaurants` - List all restaurants
- `GET /api/v1/health` - Health check endpoint
- Type-safe optional parameters across recommendation endpoints

#### Utilities
- **Logger utility** (`utils/logger.py`)
  - Structured JSON logging
  - Correlation ID support
  - Consistent formatting across services

### Changed

#### Code Quality & Type Safety
- Fixed all Pylance type errors across codebase
- Added Optional types for nullable parameters
- Implemented proper SQL NULL comparisons with `.is_(None)` and `.is_not(None)`
- Guards against None returns from database lookups
- OpenAI SDK typing fixes with cast(Any, msg) workaround
- NumPy array conversions for tensor-to-list operations

#### Services
- **recommendation_service.py**
  - Optional types for restaurant_id, budget, time_of_day parameters
  - time_decay_score accepts Optional[datetime]
  
- **gpt_helper.py**
  - Simplified content extraction from OpenAI responses
  - Removed overly defensive getattr patterns
  - Message type casting for SDK compatibility

- **feedback_service.py**
  - Added guards against None MenuItem lookups
  - Raises ValueError when items not found

- **features.py**
  - Optional[List[str]] for explicit_allergens parameter

#### Database Operations
- Replaced `== None` and `!= None` with proper SQLModel methods
- All SQL NULL comparisons use `.is_(None)` and `.is_not(None)`

#### Batch Processing
- EmbeddingService.generate_batch() uses true batch API calls
- Scripts use batch processing instead of one-by-one loops
- Massive performance improvement: ~50x faster for large datasets

### Fixed
- Import errors when running scripts inside Docker containers
- sys.path handling in data/seed.py for container execution
- Tensor-to-list conversion issues with sentence-transformers
- UMAP sparse matrix handling with np.asarray conversion
- Database duplicate declaration errors

### Documentation
- `PHASE_1_1_TEST_GUIDE.md` - Complete testing instructions
- `PHASE_1_1_SUMMARY.md` - Implementation summary
- `FIXES_APPLIED.md` - Record of Alembic removal and fixes
- `docs/HANDOVER.md` - Comprehensive handover for next AI agent
- `docs/MIGRATION_PLAN.md` - 6-phase, 12-week roadmap

### Performance
- Embedding generation: 1,000 items in ~10 seconds (was ~8 minutes)
- Batch API calls: N/100 calls instead of N calls
- Vector similarity queries: <50ms on small datasets
- FAISS index build time: Target <5s for 10K items (ready for Phase 1.2)

---

## [Unreleased] - Next Steps

### Phase 1.2 - FAISS Integration (In Progress)
- FAISS service implementation
- Index builder script
- Similar items API endpoint

### Phase 1.3 - Index Maintenance
- Automatic index refresh on new items
- Index versioning
- Incremental updates

### Phase 2 - Retrieval & Reranking
- KNN retrieval replacing cosine similarity
- LLM-driven reranking
- Contextual diversity (time, budget, mood)
- Per-dish explanations

### Phase 3 - Continuous Feedback Loop
- Real-time profile updates on every interaction
- Profile summarization with LLM
- Embedding drift monitoring

### Phase 4 - MCP Server Integration
- Tool registry and context manager
- Multi-provider LLM adapter
- Pipeline orchestration

### Phase 5 - Infrastructure
- Redis caching active
- Background jobs (Celery/APScheduler)
- Observability and metrics

### Phase 6 - Cloud Deployment
- AWS/GCP architecture
- S3/GCS for FAISS indexes
- CI/CD pipeline
- Blue-green deployment
