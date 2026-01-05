# TODO

Priority tasks for completing the TasteBud neural hybrid recommendation system.

## 🔴 Critical (Phase 1.2-1.3) - FAISS Integration

### FAISS Service Implementation
- [x] Create `services/faiss_service.py`
  - [x] Build FAISS index from embeddings
  - [x] Save/load index from disk
  - [x] Query interface with k-nearest neighbors
  - [x] Support both full (1536) and reduced (64) embeddings
  - [x] Index versioning and metadata

### FAISS Scripts
- [ ] Create `scripts/build_faiss_index.py`
  - [ ] Load all MenuItems with embeddings
  - [ ] Build index (prefer reduced_embedding if available)
  - [ ] Save to `data/faiss_indexes/current.faiss`
  - [ ] Print build stats and performance metrics

### API Endpoints
- [ ] Add `GET /api/v1/items/{item_id}/similar`
  - [ ] Load FAISS index
  - [ ] Query for k-nearest neighbors
  - [ ] Return MenuItem objects with distances
  - [ ] Optional filters (cuisine, dietary, budget)

### Index Maintenance
- [ ] Implement index refresh strategy
  - [ ] On-demand rebuild endpoint
  - [ ] Incremental updates for new items
  - [ ] Background job for periodic refresh

### Testing
- [x] Unit tests for FAISSService
- [ ] Integration tests for similar items endpoint
- [x] Performance benchmarks (query time, index size)
- [ ] Update PHASE_1_2_TEST_GUIDE.md

---

## 🟡 High Priority (Phase 2) - Retrieval & Reranking

### KNN Retrieval Service
- [ ] Create `services/retrieval_service.py`
  - [ ] Replace cosine similarity with FAISS kNN
  - [ ] Pre-filtering for allergies/diet before query
  - [ ] Candidate retrieval (top-K=50)
  - [ ] Fallback to SQL query if FAISS unavailable

### Reranking Service
- [ ] Create `services/reranking_service.py`
  - [ ] LLM-driven reranking with diversity
  - [ ] Contextual scoring (time, budget, mood)
  - [ ] MMR with enhanced diversity penalty
  - [ ] Confidence scores

### Explanation Service
- [ ] Create `services/explanation_service.py`
  - [ ] Per-dish explanations via LLM
  - [ ] Template caching for efficiency
  - [ ] Multi-language support prep

### Update Recommendation Pipeline
- [ ] Integrate retrieval_service into recommendation_service
- [ ] Add reranking step
- [ ] Generate explanations for top-N
- [ ] Update response schema with confidence + explanations

---

## 🟢 Medium Priority (Phase 3) - Continuous Feedback

### Profile Update Service
- [ ] Real-time profile vector updates
- [ ] Recency weighting with exponential decay
- [ ] Interaction history storage

### Profile Summarization
- [ ] Create `services/profile_summarization_service.py`
  - [ ] Periodic LLM summarization
  - [ ] Token threshold triggers
  - [ ] Profile drift detection

### Embedding Drift Monitor
- [ ] Create `services/drift_monitor.py`
  - [ ] Track profile evolution
  - [ ] Alert on significant drift
  - [ ] ProfileSnapshot versioning

---

## 🔵 Lower Priority (Phase 4-5) - Infrastructure

### MCP Server Integration
- [ ] Create `mcp/server.py` with tool registry
- [ ] Tool implementations (profile, menu, embeddings)
- [ ] Context manager for state
- [ ] LLM provider adapter

### Redis Caching
- [ ] Cache service wrapper
- [ ] Cache FAISS results
- [ ] Cache embeddings
- [ ] Cache recommendations
- [ ] Invalidation strategy

### Background Jobs
- [ ] Setup APScheduler or Celery
- [ ] Embedding refresh job
- [ ] Index rebuild job
- [ ] Profile summarization job

### Observability
- [ ] Prometheus metrics
- [ ] `/metrics` endpoint
- [ ] Correlation ID propagation
- [ ] Performance monitoring

---

## 🟣 Future (Phase 6) - Cloud Deployment

### Cloud Architecture
- [ ] Document AWS/GCP deployment strategy
- [ ] Terraform/CDK templates
- [ ] Security: IAM, secrets, VPC

### S3/GCS Integration
- [ ] Upload FAISS indexes to cloud storage
- [ ] Lazy-load on Lambda cold start
- [ ] Index versioning in cloud

### CI/CD
- [ ] GitHub Actions workflows
- [ ] Automated testing
- [ ] Blue-green deployment
- [ ] Deployment scripts

---

## 📝 Documentation

- [ ] API v2 documentation with new endpoints
- [ ] Architecture diagrams (current state)
- [ ] Performance benchmarks document
- [ ] Deployment guide
- [ ] Developer onboarding guide
- [ ] Update README with new setup instructions

---

## 🧪 Testing

- [ ] Unit tests for all services
- [ ] Integration tests for pipeline
- [ ] End-to-end recommendation tests
- [ ] Load testing (1M items)
- [ ] Offline evaluation metrics (recall@K, nDCG)

---

## 🐛 Known Issues

- [ ] UMAP requires 64+ items (expected, not a bug)
- [ ] Local sentence-transformers downloads model on first use (~100MB)
- [ ] No index maintenance yet (manual rebuild required)
- [ ] No Redis caching active (prepared but not used)
- [ ] No background jobs (all synchronous)
- [ ] SQL comparison warnings still use `== None` in some files (need audit)

---

## 🔧 Code Quality

- [ ] Audit all SQL comparisons for `.is_(None)` usage
- [ ] Add more type hints to legacy code
- [ ] Extract magic numbers to config
- [ ] Add docstrings to complex functions (only when truly necessary)
- [ ] Performance profiling and optimization
- [ ] Security audit (SQL injection, input validation)

---

## 📊 Metrics & Monitoring

- [ ] Define success metrics per phase
- [ ] Track recommendation quality over time
- [ ] Monitor API latency
- [ ] Track embedding generation costs
- [ ] User engagement metrics
- [ ] A/B testing framework

---

## Notes

- Prioritize Phase 1.2 (FAISS) before moving to Phase 2
- Keep Docker-first approach for all development
- Maintain clean code principles (no comments, type hints, fail-fast)
- Test after every significant change
- Update test guides with new features
- Follow semantic versioning for releases
