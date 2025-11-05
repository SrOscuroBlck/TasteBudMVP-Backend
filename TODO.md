# TODO / Roadmap

A living checklist of next steps and improvements for TasteBudBackend.

**Note:** See `MIGRATION_PLAN.md` for the comprehensive neural hybrid architecture migration roadmap.

---

## 🚀 PRIORITY: Neural Architecture Migration (see MIGRATION_PLAN.md)

### Phase 1: Foundation (Weeks 1-2) - IN PROGRESS
- [ ] Migrate to PostgreSQL with pgvector extension
- [ ] Build embedding generation service (OpenAI or sentence-transformers)
- [ ] Create batch embedding pipeline for menu items
- [ ] Integrate FAISS for approximate nearest neighbor search
- [ ] Add UMAP dimensionality reduction

### Phase 2: Retrieval & Reranking (Weeks 3-4)
- [ ] Replace cosine similarity with FAISS kNN retrieval
- [ ] Implement LLM-driven reranking with diversity
- [ ] Add contextual explanation generation per recommendation

### Phase 3: Continuous Feedback Loop (Weeks 5-6)
- [ ] Real-time profile updates on every interaction
- [ ] Automated profile summarization with LLM
- [ ] Embedding drift monitoring and alerts

### Phase 4: MCP Server Integration (Weeks 7-8)
- [ ] Build MCP server with tool registry
- [ ] Add LLM provider adapter (multi-provider support)
- [ ] Implement recommendation pipeline orchestrator

### Phase 5: Infrastructure & Observability (Weeks 9-10)
- [ ] Add Redis caching layer
- [ ] Background jobs (Celery or APScheduler)
- [ ] Metrics and monitoring (Prometheus or JSON logs)

### Phase 6: Cloud Readiness (Weeks 11-12)
- [ ] Document cloud deployment strategy
- [ ] S3/GCS for FAISS index storage
- [ ] CI/CD pipeline (GitHub Actions)

---

## Reliability & Safety
- [ ] Stronger validation for GPT outputs (Pydantic schemas) with strict parsing and safe fallbacks
- [ ] Input validation + error model across all routes (consistent 4xx/5xx payloads)
- [ ] Rate limiting/throttling on GPT endpoints and recommendation calls
- [ ] Observability: structured logging, request IDs, and correlation for GPT calls
- [ ] Add health/readiness checks for DB connectivity and migrations

## Data & Models
- [ ] Expand canonical ingredient registry (coverage for cuisines/allergens) and dietary rules
- [ ] Popularity tracking with time decay from interactions/ratings (persist and influence scoring)
- [ ] Cold-start priors enrichment per cuisine and time-of-day
- [ ] Better provenance/confidence handling for GPT-inferred items

## Product & APIs
- [ ] OpenAPI descriptions on route models (tags, summaries, examples)
- [ ] Pagination and filtering for menus and recommendations
- [ ] Authn/Authz (API key/JWT) and per-tenant isolation (multi-restaurant support)
- [ ] Idempotency keys for ingestion to avoid duplicates
- [ ] Soft-delete or archival for items and restaurants

## Performance
- [ ] Caching layer for repeat recommendations (user x restaurant x context)
- [ ] Vectorization optimizations and potential ANN if menu scale grows
- [ ] Background jobs for recalculations (popularity decay, model updates)

## Ops & Tooling
- [ ] CI: lint + type check + tests (GitHub Actions)
- [ ] Pre-commit hooks (ruff/black/isort, mypy)
- [ ] Secret scanning and dependency audit
- [ ] Branch protections (required checks), CODEOWNERS
- [ ] Production environment config (gunicorn/uvicorn workers, DB pool sizing)

## Testing
- [ ] Unit tests for safety filters, feature building, onboarding math
- [ ] Integration tests for onboarding -> recommendation flow
- [ ] Load test a few recommendation scenarios

## DX & Docs
- [ ] Postman/Insomnia collection and example envs
- [ ] API examples per endpoint in README with sample payloads
- [ ] Changelog and contribution guide
