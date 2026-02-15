# TasteBud Backend -- Architecture

## Overview

TasteBud is a personalized food recommendation system. It learns each user's taste preferences through an onboarding flow and ongoing feedback, then recommends menu items from restaurants using a multi-stage pipeline: candidate retrieval, scoring, diversity reranking, meal composition, and explanation generation.

The backend is a Python FastAPI application backed by PostgreSQL (with the pgvector extension) and FAISS for approximate nearest-neighbor search. OpenAI GPT is used for taste vector inference, onboarding question generation, and recommendation explanations.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI (Python 3.10) |
| ORM | SQLModel (SQLAlchemy under the hood) |
| Database | PostgreSQL 16 with pgvector extension |
| Vector Search | FAISS (64D reduced and 1536D full-dimension indexes) |
| LLM | OpenAI GPT (gpt-5-mini) |
| Cache | Redis 7 |
| PDF Processing | pdfplumber, Tesseract OCR |
| Deployment | Docker Compose |

---

## Directory Structure

```
TasteBudBackend/
    main.py                   # Application entry point, lifespan, router mounting
    config/
        settings.py           # Environment variable loading (Pydantic BaseSettings)
        config.yaml           # Default configuration values
        config_loader.py      # YAML config loader
        database.py           # Engine, session factory, table creation
    models/                   # SQLModel table definitions
    routes/                   # FastAPI routers (API layer)
    services/                 # Business logic (domain-organized)
    utils/                    # Cross-cutting concerns
    middleware/               # Request/response middleware
    scripts/                  # Offline batch jobs and admin tools
    data/                     # FAISS indexes, UMAP reducer, seed data
    tests/                    # Integration test scripts
    uploads/                  # Uploaded menu PDFs
    static/                   # Static file serving
    docs/                     # This documentation
```

---

## Service Domain Organization

All business logic lives under `services/`, organized into domain packages:

```
services/
    core/               Recommendation pipeline orchestration
    features/           Feature extraction, embeddings, FAISS, GPT helpers
    learning/           User taste profile updates and feedback processing
    composition/        Meal assembly (multi-course), query parsing, harmony
    diversity/          MMR reranking, cross-encoder similarity
    user/               Authentication, onboarding, interaction history, archetypes
    ingestion/          PDF upload, menu text extraction, structured parsing
    explanation/        Recommendation rationale text generation
    context/            Time-of-day signals, menu metadata
    evaluation/         Confidence scoring, A/B test interleaving, metrics
    ml/                 ML reranking model, UMAP dimensionality reduction
    infrastructure/     FAISS index maintenance, similarity matrix, scheduling
    communication/      Email follow-up, rating reminders
```

### Core Services

**RecommendationService** (`services/core/recommendation_service.py`) is the central orchestrator. It wires the full pipeline and is the entry point for all recommendation requests. It depends on 14 other services.

**RetrievalService** (`services/core/retrieval_service.py`) performs candidate retrieval via FAISS approximate nearest-neighbor search with a SQL fallback when no index is available.

**RerankingService** (`services/core/reranking_service.py`) scores candidates using taste cosine similarity, cuisine affinity, popularity, time-of-day context, and Bayesian profile sampling.

**SessionService** (`services/core/session_service.py`) manages recommendation session lifecycle: start, iterate (next batch), record feedback, complete, and abandon.

### Supporting Services

| Domain | Key Services | Purpose |
|---|---|---|
| features | FAISSService, EmbeddingService, features.py, gpt_helper.py | Vector search, embeddings, pure scoring functions, LLM calls |
| learning | BayesianProfileService, UnifiedFeedbackService, InSessionLearningService | Bayesian taste profile management, feedback processing, real-time session adjustments |
| composition | MealCompositionService, HarmonyService, QueryParsingService | Multi-course meal assembly, flavor harmony scoring, natural language query parsing |
| diversity | MMRService, CrossEncoderService | Maximum Marginal Relevance reranking for result diversity |
| user | OnboardingService, AuthService, InteractionHistoryService, ArchetypeService | User lifecycle from signup through taste profile initialization |
| ingestion | IngestionOrchestrator, PDFProcessor, MenuParser | PDF menu upload, text extraction, LLM-based structured parsing |
| explanation | ExplanationService, ExplanationEnhancementService, PersonalizedExplanationService | Generate human-readable recommendation rationales |
| context | ContextEnhancementService, MenuService | Time, occasion, and environmental signals |
| evaluation | ConfidenceService, EvaluationMetricsService, TeamDraftInterleavingService | Recommendation confidence scoring and A/B testing |

---

## Request Flow

### Recommendation Request (Simplified)

```
Client request
    |
    v
routes/sessions.py  (POST /sessions/{id}/next)
    |
    v
RecommendationService.recommend_with_session()
    |
    +---> RetrievalService.retrieve()
    |         |
    |         +---> FAISSService.search()  (ANN candidate retrieval)
    |         +---> SQL fallback if no FAISS index
    |         +---> Filter: allergens, dietary violations
    |
    +---> RerankingService.rerank()
    |         |
    |         +---> Taste cosine similarity
    |         +---> Cuisine affinity scoring
    |         +---> Popularity weighting
    |         +---> Bayesian profile sampling (exploration/exploitation)
    |
    +---> MLRerankingService.rerank()  (trained model, optional)
    |
    +---> MMRService.rerank()
    |         |
    |         +---> Maximal Marginal Relevance for diversity
    |         +---> Cuisine caps, price range constraints
    |
    +---> MealCompositionService.compose()  (if full meal intent)
    |         |
    |         +---> Appetizer + Main + Dessert assembly
    |         +---> Flavor harmony scoring
    |
    +---> ExplanationService.explain()
    |         |
    |         +---> LLM-generated rationale per item
    |
    +---> InSessionLearningService.adjust()
              |
              +---> Real-time preference shifts from session feedback
```

### User Onboarding Flow

```
POST /onboarding/start
    |
    v
OnboardingService.start()
    +---> Create user if not exists
    +---> Initialize Bayesian taste profile with population priors
    +---> Generate first "Would You Rather?" question (GPT-assisted)
    |
    v
POST /onboarding/answer  (repeated up to 7 times)
    |
    v
OnboardingService.answer()
    +---> Update taste vector axes based on chosen option
    +---> Reduce uncertainty on targeted axes
    +---> Check early-stop confidence threshold (0.8)
    +---> If not converged: generate next question targeting highest-uncertainty axis
    +---> If converged: assign taste archetype, mark onboarding complete
```

### Menu Ingestion Flow

```
POST /ingestion/upload/pdf
    |
    v
IngestionOrchestrator.process()
    +---> PDFProcessor.extract()       (pdfplumber + Tesseract OCR)
    +---> MenuParser.parse()           (GPT structured extraction)
    +---> Feature extraction            (taste vectors, texture, richness)
    +---> EmbeddingService.embed()     (OpenAI embeddings, 1536D)
    +---> Persist MenuItem records to database
```

---

## Data Architecture

### Taste Representation

Each user and menu item has a multi-dimensional taste representation:

- **Taste vector** (7 dimensions): sweet, sour, salty, bitter, umami, fatty, spicy -- each value in [0, 1]
- **Texture vector** (3 dimensions): crunchy, creamy, chewy -- each value in [0, 1]
- **Richness** (1 dimension): scalar in [0, 1]

Users also maintain:
- **Cuisine affinity**: a dictionary mapping cuisine names to preference scores
- **Ingredient penalties**: learned per-ingredient negative weights from cross-restaurant feedback
- **Permanently excluded items**: items the user has explicitly and permanently rejected

### Bayesian Taste Profile

Each user has a `BayesianTasteProfile` that models preferences as Beta distributions (one per taste axis). This enables:

- **Thompson Sampling**: drawing from the posterior to balance exploration vs. exploitation
- **Uncertainty tracking**: knowing which taste axes need more data
- **Principled updates**: Bayesian posterior updates from each feedback signal

### Embeddings and Indexes

Menu items have two embedding representations:

- **1536D embeddings**: from OpenAI text-embedding model, stored in pgvector column
- **64D reduced embeddings**: UMAP-reduced version for faster FAISS search

FAISS indexes are built offline and loaded at application startup. They support approximate nearest-neighbor retrieval for candidate generation.

---

## Application Lifecycle

On startup (`main.py` lifespan):

1. Enable pgvector extension in PostgreSQL
2. Create all SQLModel tables (handles fresh databases)
3. Run incremental schema migrations (column additions, index creation)
4. Load FAISS index (tries 64D first, falls back to 1536D, warns if neither exists)
5. Mount static file directory

On shutdown: graceful cleanup.

---

## Configuration

Configuration is loaded from two sources:

1. **Environment variables** -- processed by `config/settings.py` (Pydantic BaseSettings)
2. **config.yaml** -- default values loaded by `config/config_loader.py`

Environment variables take precedence. Key variables:

| Variable | Purpose | Default |
|---|---|---|
| `TASTEBUD_DATABASE_URL` | PostgreSQL connection string | `sqlite:///./tastebud.db` |
| `OPENAI_API_KEY` | OpenAI API key for GPT and embeddings | None |
| `OPENAI_MODEL` | GPT model name | `gpt-5-mini` |
| `HOST` | Server bind address | `0.0.0.0` |
| `PORT` | Server port | `8010` |
| `DEBUG` | Debug mode | `false` |
| `ALLOWED_ORIGINS` | CORS origins (comma-separated) | `*` |
| `MMR_ALPHA` | MMR relevance vs. diversity tradeoff | `0.7` |
| `EXPLORATION_COEFFICIENT` | Bayesian exploration strength | `0.2` |

Full list of tuning parameters is in `config/config.yaml`.

---

## Routing Layer

All routes are mounted under `/api/v1` in `main.py`:

| Router File | Prefix | Responsibility |
|---|---|---|
| `routes/api.py` | `/api/v1` | Auth, onboarding, users, restaurants, menus, recommendations, search, item details |
| `routes/sessions.py` | `/api/v1/sessions` | Session lifecycle (start, next, feedback, composition, complete, abandon, history) |
| `routes/feedback.py` | `/api/v1/feedback` | Post-meal feedback, pending feedback, email-token feedback |
| `routes/ingestion.py` | `/api/v1/ingestion` | Restaurant/menu CRUD, PDF upload, upload status |
| `routes/admin_rebuild.py` | `/api/v1/admin/rebuild` | FAISS index and similarity matrix rebuild triggers |

Two additional routers (`health.py`, `admin_index.py`) are defined but not currently mounted.

---

## Utilities

| File | Purpose |
|---|---|
| `utils/logger.py` | Structured JSON logging setup |
| `utils/circuit_breaker.py` | Circuit breaker pattern for external service calls |
| `utils/correlation_id.py` | Request correlation ID propagation |
| `utils/culinary_rules.py` | Culinary domain rules (flavor pairings, course ordering) |
| `utils/fallback.py` | Fallback strategies when services are unavailable |
| `utils/file_handler.py` | File upload handling |
| `utils/prometheus_metrics.py` | Prometheus metrics collection |
| `utils/timing.py` | Request timing decorators |

---

## Scripts

Offline batch jobs and admin tools, organized under `scripts/`:

| Directory | Scripts | Purpose |
|---|---|---|
| `scripts/migrations/` | 7 migration scripts | Incremental schema changes (columns, indexes, type fixes) |
| `scripts/data_generation/` | build_faiss_index, build_similarity_matrix, cluster_taste_archetypes, generate_embeddings | Offline index and embedding generation |
| `scripts/maintenance/` | regenerate_taste_vectors_llm | Recompute LLM-based taste vectors |
| `scripts/admin/` | reset_user, validate_config | Admin utilities |
