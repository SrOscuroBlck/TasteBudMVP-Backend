# Migration Plan: Neural Hybrid Architecture for Food Recommendation

## Executive Summary

This plan transitions TasteBud from a simple cosine-similarity backend to a **neural hybrid recommendation system** as described in the thesis. We'll implement this incrementally, starting with local infrastructure and preparing for cloud deployment.

---

## Current State Analysis

### ✅ What We Have
- FastAPI backend with REST endpoints
- SQLModel/SQLite persistence (User, MenuItem, Restaurant, Feedback)
- Basic onboarding with taste vector (10 axes)
- Cosine similarity scoring + cuisine affinity + popularity
- MMR diversification
- GPT for question generation and rationales
- Feedback learning with small adjustments

### ❌ What We're Missing (Per Thesis Architecture)
1. **Embeddings System**: No vector embeddings for dishes (using UMAP dimensionality reduction)
2. **FAISS Index**: No approximate nearest neighbor search
3. **Offline Embedding Pipeline**: No batch processing of menu embeddings
4. **Continuous Feedback Loop**: Limited profile updates (only on explicit feedback)
5. **Advanced Reranking**: Simple MMR, not LLM-driven with diversity + explanations
6. **MCP Server Integration**: No tool registry or context manager
7. **KNN Retrieval**: No k-nearest neighbors candidate retrieval phase
8. **PostgreSQL with Vector Extension**: Using SQLite (no pgvector support)

---

## Architecture Phases

### **Phase 1: Foundation (Local - Weeks 1-2)**
Goal: Set up vector database foundation and embeddings pipeline

#### 1.1 Database Migration (SQLite → PostgreSQL with pgvector)
- Install PostgreSQL locally via docker-compose (already have docker-compose.yml)
- Add `pgvector` extension to enable vector similarity search
- Migrate schema to include `embedding` vector columns on `MenuItem`
- Update SQLModel models to support vector fields

**Deliverables:**
- `docker-compose.yml` updated with pgvector-enabled Postgres image
- Migration script: `alembic` for schema versioning
- `models/restaurant.py`: Add `embedding: Optional[List[float]]` field

#### 1.2 Offline Embeddings Pipeline
- Create embedding generation service using sentence-transformers or OpenAI embeddings
- Build batch processor to embed existing menu items
- Store embeddings in PostgreSQL vector column
- Create UMAP dimensionality reducer (from high-dim to 64-dim as per thesis)

**Deliverables:**
- `services/embedding_service.py`: Generate embeddings from dish metadata
- `services/umap_reducer.py`: Dimensionality reduction (512 → 64 dims)
- `scripts/generate_embeddings.py`: Batch embedding pipeline
- `models/restaurant.py`: Update `MenuItem` with `embedding` and `reduced_embedding`

#### 1.3 FAISS Index Integration (Local)
- Install FAISS (CPU version for local)
- Build FAISS index from reduced embeddings
- Implement index persistence (save/load from disk)
- Add index refresh mechanism

**Deliverables:**
- `services/faiss_service.py`: Build, save, load, query FAISS index
- `scripts/build_faiss_index.py`: CLI to rebuild index
- Store index files in `data/faiss_indexes/`

---

### **Phase 2: Retrieval & Reranking (Local - Weeks 3-4)**

#### 2.1 KNN Retrieval Layer
- Replace cosine similarity with FAISS kNN search
- Implement candidate retrieval (top-K from FAISS, e.g., K=50)
- Add pre-filtering for safety (allergies/diet) before FAISS query

**Deliverables:**
- `services/retrieval_service.py`: KNN retrieval with pre-filters
- Update `recommendation_service.py` to use retrieval_service
- Benchmarking: Compare old vs new retrieval speed

#### 2.2 Advanced Reranking with LLM
- Implement LLM-driven reranking (per thesis: diversity + explanations)
- Add MMR with contextual diversity (time-of-day, cuisine variety, price range)
- Generate final Top-N with rationales via LLM prompt engineering

**Deliverables:**
- `services/reranking_service.py`: LLM reranking with diversity scoring
- Update `gpt_helper.py` with reranking prompts
- Add `context` to recommendations: time_of_day, budget, mood

#### 2.3 Explanation Generation
- Generate per-dish explanations using LLM (why this dish for this user)
- Store explanation templates for efficiency
- Add confidence scores to recommendations

**Deliverables:**
- `services/explanation_service.py`: Generate contextual explanations
- Update recommendation response schema with `explanation` and `confidence`

---

### **Phase 3: Continuous Feedback Loop (Local - Weeks 5-6)**

#### 3.1 Profile Continuous Update
- Implement real-time profile vector updates on every interaction (view, click, dismiss)
- Add recency weighting (exponential decay for old feedback)
- Store interaction history with timestamps

**Deliverables:**
- Update `feedback_service.py`: Immediate profile updates
- Add `InteractionWeight` model with decay function
- Store feedback embeddings for profile drift tracking

#### 3.2 Automated Profile Summarization (LLM)
- Periodically summarize user profile with LLM (every N interactions or token threshold)
- Store profile summary for explainability
- Trigger profile re-embedding when summary changes significantly

**Deliverables:**
- `services/profile_summarization_service.py`: LLM-based profile summary
- Add `User.profile_summary` and `User.last_summary_update` fields
- Background job: Check token threshold and trigger summarization

#### 3.3 Embedding Drift Monitoring
- Track user embedding evolution over time
- Detect significant drift and trigger re-onboarding or profile refresh
- Visualize profile evolution (optional, for debugging)

**Deliverables:**
- `services/drift_monitor.py`: Cosine distance between profile versions
- Alert system for significant drift
- Store `ProfileSnapshot` model with versioning

---

### **Phase 4: MCP Server Integration (Local - Weeks 7-8)**

#### 4.1 Tool Registry & Context Manager
- Build MCP server with tool registry (per thesis diagrams)
- Expose tools: `get_user_profile`, `get_restaurant_menu`, `get_embeddings`
- Add context manager for coordinating multi-step operations

**Deliverables:**
- `mcp/server.py`: MCP protocol server
- `mcp/tools/`: Tool implementations (profile, menu, embeddings)
- `mcp/context_manager.py`: State management across tool calls

#### 4.2 LLM Provider Adapter
- Abstract LLM calls behind provider interface (OpenAI, Anthropic, local models)
- Add retry logic and fallback models
- Token usage tracking per user/session

**Deliverables:**
- `mcp/llm_adapter.py`: Multi-provider LLM interface
- `config/llm_providers.py`: Provider configurations
- Add `usage_logs` table for tracking

#### 4.3 Recommendation Pipeline Orchestration
- Build pipeline: Retrieve (KNN) → Pre-filter → Rerank (LLM) → Diversify (MMR) → Explain (LLM) → Return
- Make pipeline configurable (skip steps, adjust weights)
- Add pipeline performance metrics

**Deliverables:**
- `services/pipeline_orchestrator.py`: Configurable recommendation pipeline
- `config/pipeline_config.py`: Pipeline stage configs
- Metrics: latency per stage, cache hit rates

---

### **Phase 5: Infrastructure & Observability (Local - Weeks 9-10)**

#### 5.1 Redis Cache Layer
- Add Redis for caching embeddings and recommendations
- Cache FAISS search results (user_id + context → candidates)
- Invalidate cache on profile updates

**Deliverables:**
- `docker-compose.yml`: Add Redis service
- `services/cache_service.py`: Redis wrapper
- Cache keys: `rec:{user_id}:{context_hash}`, `emb:{item_id}`

#### 5.2 Background Jobs (Celery or APScheduler)
- Schedule periodic tasks: embedding regeneration, FAISS index rebuild, profile summarization
- Add job queue for async operations (e.g., post-feedback profile update)

**Deliverables:**
- `workers/`: Celery workers or APScheduler jobs
- `tasks/embedding_refresh.py`, `tasks/index_rebuild.py`, `tasks/profile_summary.py`
- `docker-compose.yml`: Add Celery + Redis broker (or use APScheduler with no extra infra)

#### 5.3 Observability & Monitoring
- Structured logging with correlation IDs for all operations
- Metrics: recommendation latency, FAISS query time, LLM token usage, cache hit rate
- Health checks: DB, Redis, FAISS index status

**Deliverables:**
- `services/metrics.py`: Prometheus metrics or simple JSON logs
- `routes/monitoring.py`: `/metrics` endpoint
- Correlation ID propagation across services

---

### **Phase 6: Production Readiness (Cloud Prep - Weeks 11-12)**

#### 6.1 Cloud Architecture Prep
- Document AWS/GCP deployment strategy (per thesis diagrams)
- Plan: ELB → API Gateway → Lambda/Fargate → RDS (PostgreSQL+pgvector) → S3 (FAISS indexes)
- Security: IAM roles, secrets manager, VPC setup

**Deliverables:**
- `docs/CLOUD_DEPLOYMENT.md`: Step-by-step cloud deployment guide
- Terraform or CDK templates (scaffold)
- Environment configs: `prod.env`, `staging.env`

#### 6.2 FAISS Index to Cloud Storage
- Store FAISS indexes in S3 or GCS
- Lazy-load indexes on Lambda cold start or cache in EFS/persistent volume
- Implement index versioning

**Deliverables:**
- `services/faiss_service.py`: S3 upload/download methods
- Index versioning schema: `indexes/v{timestamp}/faiss.index`

#### 6.3 CI/CD Pipeline
- GitHub Actions: lint, test, build, deploy
- Automated embedding pipeline trigger on menu updates
- Blue-green deployment for zero-downtime

**Deliverables:**
- `.github/workflows/ci.yml`: Lint + test + build
- `.github/workflows/deploy.yml`: Deploy to staging/prod
- Deployment scripts: `scripts/deploy_*.sh`

---

## Implementation Priorities (Local Development)

### **Immediate (Phase 1 - Week 1)**
1. ✅ Migrate to PostgreSQL with pgvector
2. ✅ Add embedding generation service (OpenAI or sentence-transformers)
3. ✅ Create batch embedding script for existing items

### **Short-term (Phase 1-2 - Weeks 2-4)**
4. ✅ Build FAISS index locally
5. ✅ Implement KNN retrieval replacing cosine similarity
6. ✅ Add LLM reranking with diversity

### **Medium-term (Phase 3 - Weeks 5-6)**
7. ✅ Continuous feedback loop with real-time profile updates
8. ✅ Profile summarization service
9. ✅ Embedding drift monitoring

### **Long-term (Phase 4-5 - Weeks 7-10)**
10. ✅ MCP server integration
11. ✅ Redis caching layer
12. ✅ Background jobs for async processing

### **Cloud Prep (Phase 6 - Weeks 11-12)**
13. ⏳ AWS/GCP architecture planning
14. ⏳ S3/GCS for FAISS indexes
15. ⏳ CI/CD and deployment automation

---

## Technology Stack Updates

### Current Stack
- FastAPI, SQLModel, SQLite, OpenAI, NumPy, httpx

### New Dependencies (Phase 1-3)
```txt
# Vector DB & Embeddings
psycopg2-binary==2.9.9
pgvector==0.2.3
sentence-transformers==2.2.2  # or use OpenAI embeddings API
umap-learn==0.5.5

# FAISS
faiss-cpu==1.7.4  # Local; faiss-gpu for production

# Caching & Jobs
redis==5.0.1
celery==5.3.4  # or apscheduler==3.10.4 for simpler setup

# Observability
prometheus-client==0.19.0

# Migrations
alembic==1.12.1
```

### New Dependencies (Phase 4-6)
```txt
# MCP Server
mcp==0.9.0  # Model Context Protocol SDK

# Cloud Storage
boto3==1.34.10  # AWS S3
google-cloud-storage==2.14.0  # GCP GCS

# Deployment
gunicorn==21.2.0
uvloop==0.19.0
```

---

## File Structure (New Additions)

```
TasteBudBackend/
├── services/
│   ├── embedding_service.py          # Generate embeddings
│   ├── umap_reducer.py                # Dimensionality reduction
│   ├── faiss_service.py               # FAISS index management
│   ├── retrieval_service.py           # KNN retrieval
│   ├── reranking_service.py           # LLM reranking
│   ├── explanation_service.py         # Generate explanations
│   ├── profile_summarization_service.py  # LLM profile summary
│   ├── drift_monitor.py               # Profile drift tracking
│   ├── cache_service.py               # Redis caching
│   ├── metrics.py                     # Observability metrics
│   └── pipeline_orchestrator.py       # Recommendation pipeline
├── mcp/
│   ├── server.py                      # MCP server
│   ├── context_manager.py             # State management
│   ├── llm_adapter.py                 # Multi-provider LLM
│   └── tools/
│       ├── profile_tool.py
│       ├── menu_tool.py
│       └── embeddings_tool.py
├── workers/
│   ├── celery_app.py                  # Celery config
│   └── tasks/
│       ├── embedding_refresh.py
│       ├── index_rebuild.py
│       └── profile_summary.py
├── scripts/
│   ├── generate_embeddings.py         # Batch embed items
│   ├── build_faiss_index.py           # Build FAISS index
│   └── migrate_to_postgres.py         # SQLite → PostgreSQL
├── data/
│   └── faiss_indexes/                 # Local FAISS storage
├── migrations/                         # Alembic migrations
├── docs/
│   ├── ARCHITECTURE.md                # System architecture
│   ├── CLOUD_DEPLOYMENT.md            # Cloud deployment guide
│   └── API_V2.md                      # Updated API docs
├── tests/
│   ├── test_embeddings.py
│   ├── test_faiss.py
│   ├── test_retrieval.py
│   └── test_pipeline.py
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
├── docker-compose.yml                  # Add Redis, Postgres with pgvector
├── requirements.txt                    # Updated dependencies
├── MIGRATION_PLAN.md                   # This file
└── TODO.md                             # Existing todos (update)
```

---

## Risk Mitigation

### Technical Risks
1. **FAISS Index Size**: May grow large with many items → Solution: IVFPQ compression
2. **LLM Latency**: Reranking may slow recommendations → Solution: Cache, parallel calls, timeouts
3. **Embedding Quality**: Poor embeddings = poor recommendations → Solution: Evaluate with offline metrics (recall@K, nDCG)
4. **Profile Drift**: Overfitting to recent interactions → Solution: Decay old feedback, periodic re-onboarding

### Operational Risks
1. **Local Resource Limits**: FAISS + embeddings memory-intensive → Solution: Start small, profile memory usage
2. **Migration Complexity**: SQLite → PostgreSQL data loss risk → Solution: Backup, dry-run, validation scripts
3. **Dependency Hell**: Many new packages → Solution: Pin versions, use virtual env, test in isolation

---

## Success Metrics

### Phase 1-2 (Embeddings & Retrieval)
- [ ] Embedding generation: <500ms per item
- [ ] FAISS index build: <5 seconds for 10K items
- [ ] KNN retrieval: <50ms for top-50 candidates

### Phase 3 (Feedback Loop)
- [ ] Profile update latency: <100ms
- [ ] Profile summarization: <2 seconds per user
- [ ] Drift detection accuracy: >90% (manual validation)

### Phase 4-5 (MCP & Infra)
- [ ] MCP server uptime: >99% local
- [ ] Cache hit rate: >80% for repeated requests
- [ ] Background job success rate: >95%

### Phase 6 (Cloud Prep)
- [ ] Cloud deployment automation: <30 min end-to-end
- [ ] Zero-downtime deployment: blue-green verified

---

## Next Steps (Week 1 Action Items)

1. **Setup PostgreSQL with pgvector**
   - Update `docker-compose.yml` with `pgvector/pgvector:pg16` image
   - Create `scripts/migrate_to_postgres.py` to copy SQLite data
   - Test vector column creation and basic queries

2. **Embedding Service MVP**
   - Implement `services/embedding_service.py` using OpenAI embeddings API
   - Add `embedding` field to `MenuItem` model
   - Create `scripts/generate_embeddings.py` to embed seed data

3. **FAISS Index POC**
   - Install `faiss-cpu`
   - Create `services/faiss_service.py` with build/save/load/query
   - Test index with 100 items, measure query latency

4. **Update Documentation**
   - Add architecture diagrams to `docs/ARCHITECTURE.md`
   - Document new endpoints in `docs/API_V2.md`
   - Update `README.md` with new setup instructions

---

## Questions to Address

1. **Embedding Model**: Use OpenAI embeddings (expensive, high-quality) or sentence-transformers (free, local)? → Recommend: Start with OpenAI, switch to local if budget is a concern
2. **FAISS Index Type**: Flat (exact) vs IVFPQ (approximate)? → Recommend: Start Flat, switch to IVFPQ if >100K items
3. **Background Jobs**: Celery (robust, requires Redis) vs APScheduler (simple, in-process)? → Recommend: APScheduler for local, Celery for cloud
4. **Profile Update Frequency**: Real-time (every interaction) vs batched (every N interactions)? → Recommend: Real-time for now, batch if latency becomes an issue

---

## References

- Thesis: "Un Modelo de Predicción para Recomendación Gastronómica"
- Architecture Diagrams: Provided images (initial profiling, continuous updates, recommendation pipeline, infrastructure)
- FAISS Documentation: https://github.com/facebookresearch/faiss/wiki
- pgvector Documentation: https://github.com/pgvector/pgvector
- MCP Protocol: https://modelcontextprotocol.io/

---

**Prepared by:** GitHub Copilot Agent  
**Date:** November 5, 2025  
**Version:** 1.0
