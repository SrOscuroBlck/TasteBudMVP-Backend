# TasteBud Backend

Personalized food recommendation system. Users build a taste profile through onboarding and ongoing feedback, then receive recommendations from restaurant menus ranked by taste similarity, cuisine affinity, popularity, and Bayesian exploration -- with MMR diversity reranking and optional meal composition.

## Tech Stack

- **Framework**: FastAPI (Python 3.10)
- **Database**: PostgreSQL 16 with pgvector
- **Vector Search**: FAISS (64D and 1536D indexes)
- **LLM**: OpenAI GPT (gpt-5-mini) for onboarding, taste inference, explanations
- **Cache**: Redis 7
- **Deployment**: Docker Compose

## Quick Start

```bash
# Start PostgreSQL and Redis
docker compose up -d postgres redis

# Install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env  # Edit with your OPENAI_API_KEY

# Run the API
uvicorn main:app --reload --host 0.0.0.0 --port 8010
```

Or run everything in Docker:

```bash
docker compose up -d
```

API available at `http://localhost:8010`. Interactive docs at `http://localhost:8010/docs`.

## Documentation

| Document | Description |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture, service domains, request flows, configuration |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | Complete API endpoint reference with request/response examples |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Database models, relationships, and column definitions |
| [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) | Setup, running, testing, adding features, troubleshooting |
| [docs/RECOMMENDATION_PIPELINE.md](docs/RECOMMENDATION_PIPELINE.md) | How the recommendation algorithm works stage by stage |

## Project Structure

```
main.py                 Application entry point
config/                 Settings, database, config.yaml
models/                 SQLModel table definitions
routes/                 FastAPI routers (API layer)
services/               Business logic, organized by domain:
    core/                 Recommendation pipeline orchestration
    features/             Embeddings, FAISS, feature functions, GPT helpers
    learning/             Bayesian profiles, feedback processing
    composition/          Meal assembly, query parsing
    diversity/            MMR reranking
    user/                 Auth, onboarding, interaction history
    ingestion/            PDF processing, menu parsing
    explanation/          Recommendation rationale generation
    context/              Time-of-day and contextual signals
    evaluation/           Confidence scoring, A/B testing
    ml/                   ML reranking, UMAP
    infrastructure/       Index maintenance, scheduling
    communication/        Email follow-ups
utils/                  Logger, circuit breaker, timing, correlation IDs
scripts/                Migrations, data generation, admin tools
tests/                  Integration test scripts
```

## License

Internal project.
