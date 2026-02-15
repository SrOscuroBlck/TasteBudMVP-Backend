# TasteBud Backend -- Developer Guide

This guide covers everything needed to set up, run, and extend the TasteBud backend.

---

## Prerequisites

- Python 3.10+
- Docker and Docker Compose (for PostgreSQL and Redis)
- An OpenAI API key (required for GPT-powered features: onboarding questions, taste inference, explanations)

---

## Local Setup

### 1. Clone and Install Dependencies

```bash
cd TasteBudBackend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start Infrastructure

PostgreSQL (with pgvector) and Redis run via Docker Compose:

```bash
docker compose up -d postgres redis
```

This starts:
- PostgreSQL 16 with pgvector on port 5432 (user: `tastebud`, password: `tastebud`, database: `tastebud`)
- Redis 7 on port 6379

### 3. Configure Environment

Create a `.env` file in the project root:

```
TASTEBUD_DATABASE_URL=postgresql+psycopg2://tastebud:tastebud@localhost:5432/tastebud
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5-mini
HOST=0.0.0.0
PORT=8010
DEBUG=true
ALLOWED_ORIGINS=*
```

Without `OPENAI_API_KEY`, GPT-powered features (onboarding, taste inference, explanations) will fall back to deterministic alternatives or fail gracefully.

### 4. Run the API

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8010
```

On first startup, the application will:
1. Enable the pgvector extension
2. Create all database tables
3. Run incremental schema migrations
4. Attempt to load FAISS indexes (warns if not found)

The API is available at `http://localhost:8010`. Interactive docs at `http://localhost:8010/docs`.

---

## Docker Deployment (Full Stack)

Run everything (API, PostgreSQL, Redis) in Docker:

```bash
docker compose up -d
```

The API container mounts the source directory as a volume and runs with `--reload`, so code changes are picked up automatically during development.

### Environment Variables for Docker

Set `OPENAI_API_KEY` in your shell before running Docker Compose, or create a `.env` file:

```bash
export OPENAI_API_KEY=sk-...
docker compose up -d
```

---

## Seed Data

To populate the database with sample restaurants and menu items:

```bash
python data/seed.py
```

---

## Building FAISS Indexes

Recommendation retrieval uses FAISS for approximate nearest-neighbor search. Indexes must be built after menu items are ingested.

### Generate Embeddings

First, generate OpenAI embeddings for all menu items that lack them:

```bash
python scripts/data_generation/generate_embeddings.py
```

### Build 64D Index (Recommended)

Build the UMAP-reduced 64-dimensional index (faster search, lower memory):

```bash
python scripts/data_generation/build_faiss_index.py --dimension 64
```

### Build 1536D Index

Build the full-dimensional index (slower but higher fidelity):

```bash
python scripts/data_generation/build_faiss_index.py --dimension 1536
```

### Build Similarity Matrix

Used by the MMR diversity algorithm:

```bash
python scripts/data_generation/build_similarity_matrix.py
```

Indexes can also be rebuilt at runtime via the admin API:

```
POST /api/v1/admin/rebuild/faiss-64d
POST /api/v1/admin/rebuild/faiss-1536d
POST /api/v1/admin/rebuild/similarity-matrix
POST /api/v1/admin/rebuild/all
GET  /api/v1/admin/rebuild/status
```

---

## Project Structure

```
TasteBudBackend/
    main.py                   # FastAPI app, lifespan, router mounting
    config/
        settings.py           # Environment config (Pydantic BaseSettings)
        config.yaml           # Default config values
        config_loader.py      # YAML config loader
        database.py           # SQLAlchemy engine and session
    models/                   # SQLModel table definitions
        __init__.py           # All model exports
        user.py               # User, OnboardingState, OnboardingQuestion
        restaurant.py         # Restaurant, MenuItem
        session.py            # RecommendationSession, Feedback models
        bayesian_profile.py   # BayesianTasteProfile
        feedback.py           # Rating, Interaction
        auth.py               # UserSession, OTPCode
        ingestion.py          # MenuUpload, ParsedMenuItem
        ...
    routes/                   # API endpoint definitions
        api.py                # Main router (auth, onboarding, users, etc.)
        sessions.py           # Session lifecycle endpoints
        feedback.py           # Post-meal feedback endpoints
        ingestion.py          # Menu ingestion endpoints
        admin_rebuild.py      # Index rebuild endpoints
    services/                 # Business logic (see ARCHITECTURE.md)
        core/                 # Recommendation pipeline
        features/             # Embeddings, FAISS, feature functions
        learning/             # Taste profile and feedback processing
        composition/          # Meal assembly, query parsing
        diversity/            # MMR, cross-encoder
        user/                 # Auth, onboarding, interaction history
        ingestion/            # PDF processing, menu parsing
        explanation/          # Recommendation explanations
        context/              # Contextual signals
        evaluation/           # Metrics, A/B testing
        ml/                   # ML reranking, UMAP
        infrastructure/       # Index management, scheduling
        communication/        # Email services
    utils/                    # Logger, circuit breaker, timing, etc.
    scripts/
        migrations/           # Schema migration scripts
        data_generation/      # Index and embedding generation
        maintenance/          # Taste vector regeneration
        admin/                # User reset, config validation
    tests/                    # Integration test scripts (shell)
```

---

## Adding a New Feature

### Adding a New API Endpoint

1. Identify the appropriate route file in `routes/` or create a new one.
2. Add the FastAPI route function.
3. Create or use existing services from `services/` for business logic.
4. If creating a new router file, mount it in `main.py`.

### Adding a New Service

1. Identify the correct domain directory under `services/`.
2. Create the service file with clear, focused responsibilities.
3. Add the export to the domain's `__init__.py`.
4. Use the service from routes or other services via direct instantiation.

### Adding a New Model

1. Add the SQLModel class in the appropriate file under `models/`.
2. Re-export it in `models/__init__.py`.
3. Tables are auto-created on startup via `create_db_and_tables()`.
4. If adding columns to an existing table, create a migration script in `scripts/migrations/`.

### Adding a Migration

For adding columns or indexes to existing tables:

1. Create a new file in `scripts/migrations/` (e.g., `migrate_add_my_column.py`).
2. Implement the migration using raw SQL via SQLAlchemy:
   ```python
   from config import engine
   from sqlalchemy import text, inspect
   from utils.logger import setup_logger

   logger = setup_logger(__name__)

   def add_my_column():
       inspector = inspect(engine)
       columns = [col["name"] for col in inspector.get_columns("my_table")]
       if "my_column" not in columns:
           with engine.begin() as conn:
               conn.execute(text("ALTER TABLE my_table ADD COLUMN my_column TEXT"))
           logger.info("Added my_column to my_table")
   ```
3. Import and call it in `main.py` lifespan.

---

## Testing

Integration tests are shell scripts in `tests/`:

| Script | Purpose |
|---|---|
| `test_complete_flow.sh` | End-to-end: onboarding, session, recommendations, feedback |
| `test_composition_feedback.sh` | Meal composition feedback flow |
| `test_dislike_persistence.sh` | Verify disliked items are excluded in future sessions |

Run with the API server active:

```bash
bash tests/test_complete_flow.sh
```

---

## Configuration Reference

All tunable parameters are in `config/config.yaml`. Key sections:

| Section | Parameters |
|---|---|
| server | host, port, debug, allowed_origins |
| database | url |
| openai | api_key, model |
| jwt | secret_key, algorithm, token expiry |
| otp | expire_minutes, max_attempts |
| onboarding | max_questions (7), early_stop_confidence (0.8), k, sigma_step |
| recommendation | lambda_cuisine (0.2), lambda_pop (0.2), mmr_alpha (0.7), gpt_confidence_discount, exploration_coefficient (0.2) |
| temporal_decay | feedback_half_life_days (21), decay_half_life_days (30) |
| faiss | index_path, dimension, maintenance interval |
| query | retrieval_candidates_multiplier, diversity_weight, cross_encoder toggle |
| mmr | diversity_weight, per-cuisine and per-restaurant caps |
| explanations | use_llm_first toggle |
| evaluation | min A/B test samples, default time period |
| observability | prometheus toggle, log_level, request_timing toggle |
| frontend | url |

Environment variables override config.yaml values. See `config/settings.py` for the full mapping.

---

## Common Tasks

### Reset a User's Profile

```bash
python scripts/admin/reset_user.py --email user@example.com
```

### Validate Configuration

```bash
python scripts/admin/validate_config.py
```

### Regenerate Taste Vectors

Recompute LLM-based taste vectors for all menu items:

```bash
python scripts/maintenance/regenerate_taste_vectors_llm.py
```

### Cluster Taste Archetypes

Generate taste archetype clusters from existing user data:

```bash
python scripts/data_generation/cluster_taste_archetypes.py
```

---

## Troubleshooting

**FAISS index not found warning on startup**: This is normal on a fresh install. Ingest some menu items, generate embeddings, and build the index (see "Building FAISS Indexes" above).

**Onboarding returns 500**: Check that `OPENAI_API_KEY` is set. The onboarding service uses GPT to generate questions. Without it, it falls back but may error on some edge cases.

**pgvector extension error**: Ensure you are using the `pgvector/pgvector:pg16` Docker image for PostgreSQL, not the standard postgres image.

**SQLite mode**: The default database URL uses SQLite. This works for basic testing but does not support pgvector (Vector columns will be ignored). Use PostgreSQL for full functionality.

**CORS errors from frontend**: Set `ALLOWED_ORIGINS` to the frontend URL (e.g., `http://localhost:5173`) or `*` for development.
