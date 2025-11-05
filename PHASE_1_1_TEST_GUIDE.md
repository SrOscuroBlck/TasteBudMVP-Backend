# Phase 1 Implementation - Test Guide

**Iteration:** Phase 1.1 - Foundation Setup  
**Date:** November 5, 2025  
**Components:** Docker infrastructure, PostgreSQL+pgvector, Embedding service, UMAP reducer

---

## 🎯 What Was Built

### 1. Docker Infrastructure
- **PostgreSQL with pgvector** - Vector similarity search support
- **Redis** - Caching layer (ready for Phase 5)
- **API container** - FastAPI app with auto-migrations

### 2. Database Schema (Auto-sync)
- **SQLModel auto-sync** - Tables created automatically on startup
- **Vector columns** on `menuitem` table:
  - `embedding` (1536 dims) - Full OpenAI embedding
  - `reduced_embedding` (64 dims) - UMAP-reduced for FAISS
  - Metadata: model, version, timestamp
- **pgvector extension** enabled automatically

### 3. Embedding Service
- **OpenAI embeddings** - Primary (text-embedding-3-small)
- **Sentence-transformers** - Fallback (all-MiniLM-L6-v2)
- Rich text generation from menu items
- Batch processing support

### 4. UMAP Dimensionality Reduction
- Reduces 1536 dims → 64 dims
- Preserves similarity structure
- Saves fitted model for consistency

### 5. Scripts
- `generate_embeddings.py` - Batch embed all menu items
- `init_pgvector.sql` - Initialize pgvector extension

---

## 🚀 How to Test

### Prerequisites
Ensure you have:
- Docker and Docker Compose installed
- OpenAI API key in `.env` file
- At least 4GB RAM available

### Step 1: Environment Setup

Create or update `.env` file:
```bash
# Copy the existing .env or create new one
cat > .env << 'EOF'
TASTEBUD_DATABASE_URL=postgresql+psycopg2://tastebud:tastebud@postgres:5432/tastebud
REDIS_URL=redis://redis:6379/0
OPENAI_API_KEY=your-actual-key-here
OPENAI_MODEL=gpt-4o-mini
HOST=0.0.0.0
PORT=8010
DEBUG=true
ALLOWED_ORIGINS=*
EOF
```

**Important:** Replace `your-actual-key-here` with your real OpenAI API key from the existing `.env`.

### Step 2: Start Infrastructure

```bash
# Stop any running servers
# (If you have uvicorn running locally, stop it with Ctrl+C)

# Build and start all services
docker-compose up --build

# Or run in detached mode
docker-compose up --build -d
```

**What happens:**
1. PostgreSQL with pgvector starts
2. Redis starts
3. API container builds (installs new dependencies)
4. Alembic runs migrations (adds vector columns)
5. FastAPI starts with auto-reload

**Expected output:**
```
tastebud_postgres | database system is ready to accept connections
tastebud_redis | Ready to accept connections
tastebud_api | INFO:     CREATE EXTENSION IF NOT EXISTS vector
tastebud_api | INFO:     Application startup complete.
tastebud_api | INFO:     Uvicorn running on http://0.0.0.0:8010
```

### Step 3: Verify Database Schema

Check that vector columns were created:

```bash
# Connect to PostgreSQL
docker exec -it tastebud_postgres psql -U tastebud -d tastebud

# Check pgvector extension
\dx

# Should show:
#  vector | 0.5.1 | public | vector data type and ivfflat access method

# Check menuitem table schema
\d menuitem

# Should show new columns:
#  embedding              | vector(1536)
#  reduced_embedding      | vector(64)
#  embedding_model        | character varying
#  embedding_version      | character varying
#  last_embedded_at       | timestamp without time zone

# Exit psql
\q
```

### Step 4: Seed Sample Data

Seed the database with test restaurants and menu items:

```bash
# Run seed script inside container
docker exec -it tastebud_api python data/seed.py
```

**Expected output:**
```
Seeding database...
Created 2 restaurants
Created 10 menu items
Created 2 users
Created population stats
✓ Database seeded successfully
```

### Step 5: Generate Embeddings

Now generate embeddings for the seeded items:

```bash
# Run embedding generation script
docker exec -it tastebud_api python scripts/generate_embeddings.py
```

**Expected output:**
```
============================================================
EMBEDDING GENERATION PIPELINE
============================================================
Generating embeddings for 10 items...
  [1/10] ✓ Margherita Pizza
  [2/10] ✓ Spicy Beef Taco
  [3/10] ✓ Tofu Bowl
  ...
✓ Generated embeddings for 10 items

Reducing embeddings for 10 items using UMAP...
  ⚠ Only 10 items. UMAP works best with more data.
  Skipping dimensionality reduction for now.
  Will use full embeddings for FAISS.
✓ Complete
```

**Note:** UMAP requires ~64+ items to work well. With only 10 items, we skip reduction and will use full embeddings for now.

### Step 6: Verify Embeddings in Database

```bash
# Connect to database
docker exec -it tastebud_postgres psql -U tastebud -d tastebud

# Check that embeddings were generated
SELECT 
    name, 
    embedding IS NOT NULL as has_embedding,
    embedding_model,
    last_embedded_at
FROM menuitem
LIMIT 5;

# Should show:
#       name        | has_embedding |       embedding_model        |     last_embedded_at
# ------------------+---------------+------------------------------+--------------------------
#  Margherita Pizza | t             | text-embedding-3-small       | 2025-11-05 14:30:00
#  Spicy Beef Taco  | t             | text-embedding-3-small       | 2025-11-05 14:30:01
#  ...

# Test vector similarity (cosine distance)
SELECT name, 
       embedding <=> (SELECT embedding FROM menuitem WHERE name = 'Margherita Pizza') as distance
FROM menuitem
WHERE name != 'Margherita Pizza'
ORDER BY distance
LIMIT 3;

# Should show items similar to pizza (closer distance = more similar)

\q
```

### Step 7: Test API Endpoints

The API should be running on `http://localhost:8010`.

#### Health Check
```bash
curl http://localhost:8010/api/v1/health
```

**Expected:** `{"status":"ok","version":"0.1.0"}`

#### Get Menu with Embeddings
```bash
# Get a restaurant ID
RESTAURANT_ID=$(curl -s http://localhost:8010/api/v1/restaurants | jq -r '.[0].id')

# Get menu for that restaurant
curl "http://localhost:8010/api/v1/restaurants/${RESTAURANT_ID}/menu" | jq
```

**Expected:** List of menu items (embeddings not returned in API, stored in DB)

#### Create New Item with Auto-Embedding

We'll add this endpoint in the next iteration, but you can manually test embedding generation:

```bash
# Inside container, run Python
docker exec -it tastebud_api python

# Then:
from services.embedding_service import EmbeddingService
from models.restaurant import MenuItem
from sqlmodel import Session
from config.database import engine

svc = EmbeddingService()
test_item = {
    "name": "Green Curry",
    "description": "Thai green curry with vegetables",
    "ingredients": ["coconut milk", "green curry paste", "vegetables"],
    "cuisine": ["Thai"],
    "spice_level": 4
}

result = svc.generate_embedding(test_item)
print(f"Generated embedding with {len(result['embedding'])} dimensions")
print(f"Model: {result['embedding_model']}")
print(f"First 5 values: {result['embedding'][:5]}")
```

**Expected:**
```
Generated embedding with 1536 dimensions
Model: text-embedding-3-small
First 5 values: [0.123, -0.456, 0.789, ...]
```

### Step 8: Test Logs and Monitoring

```bash
# View API logs
docker-compose logs -f api

# View PostgreSQL logs
docker-compose logs -f postgres

# View all logs
docker-compose logs -f
```

---

## ✅ Success Criteria

After completing all steps, verify:

- [x] Docker containers running: `docker-compose ps` shows 3 services (postgres, redis, api) as "Up"
- [x] pgvector extension enabled in PostgreSQL
- [x] Migration 001 applied successfully
- [x] Vector columns exist in `menuitem` table
- [x] Sample data seeded (2 restaurants, 10 items)
- [x] Embeddings generated for all items
- [x] Embeddings stored in database (1536 dimensions)
- [x] API health endpoint returns 200 OK
- [x] Menu endpoint returns items
- [x] Vector similarity queries work in PostgreSQL

---

## 🐛 Troubleshooting

### Problem: Docker build fails with "no space left on device"
**Solution:**
```bash
docker system prune -a
docker volume prune
```

### Problem: PostgreSQL fails to start
**Solution:**
```bash
# Remove old volume
docker-compose down -v
docker-compose up --build
```

### Problem: Tables not created
**Solution:**
```bash
# Check if pgvector extension exists
docker exec -it tastebud_postgres psql -U tastebud -d tastebud -c "\dx"

# Restart API to trigger table creation
docker-compose restart api
```

### Problem: OpenAI API key error
**Solution:**
- Check `.env` file has correct `OPENAI_API_KEY`
- Restart containers: `docker-compose restart api`
- Embedding service will fall back to sentence-transformers if OpenAI fails

### Problem: UMAP fails with "too few samples"
**Expected behavior:** With <64 items, UMAP is skipped. This is fine for testing.
**Solution:** Add more seed data or skip UMAP for now (will use full embeddings)

### Problem: Port 8010 already in use
**Solution:**
```bash
# Stop local uvicorn server
# Or change port in docker-compose.yml: "8011:8010"
```

---

## 📊 Performance Benchmarks

Expected performance on local setup:

| Operation | Time | Notes |
|-----------|------|-------|
| Docker compose up | ~30-60s | First time build |
| Alembic migration | ~2s | One-time per migration |
| Seed data | ~1s | 10 items |
| Generate embedding (OpenAI) | ~200-500ms | Per item |
| Generate embedding (local) | ~50-100ms | Per item |
| UMAP fit | ~2-5s | With 100+ items |
| Vector similarity query | ~5-50ms | Depends on dataset size |

---

## 🔄 Clean Up and Reset

To start fresh:

```bash
# Stop and remove everything
docker-compose down -v

# Remove data directory
rm -rf data/faiss_indexes data/umap_reducer.joblib

# Rebuild from scratch
docker-compose up --build
```

---

## 📝 Next Steps (Phase 1.2)

In the next iteration, we'll add:
1. **FAISS service** - Fast approximate nearest neighbor search
2. **FAISS index builder** - Create searchable index from embeddings
3. **Test FAISS queries** - Search for similar dishes
4. **API endpoint** - `/api/v1/search/similar` to find similar items

---

## 🎓 What You Learned

This iteration established:
- ✅ Docker-first development (everything in containers)
- ✅ PostgreSQL with vector support (pgvector extension)
- ✅ Database migrations with Alembic
- ✅ Embedding generation pipeline
- ✅ Dimensionality reduction with UMAP
- ✅ Vector similarity search in SQL

**Clean code principles applied:**
- Single responsibility (separate services for embeddings, UMAP, DB)
- No hard-coded values (all config in .env)
- Type hints throughout
- Error handling and fallbacks
- Clear separation of concerns

---

## 📧 Questions or Issues?

If something doesn't work:
1. Check logs: `docker-compose logs -f`
2. Verify environment variables: `docker exec tastebud_api env | grep TASTEBUD`
3. Check database connection: `docker exec -it tastebud_postgres pg_isready`
4. Test OpenAI key: `docker exec -it tastebud_api python -c "from openai import OpenAI; print(OpenAI().models.list())"`

---

**Status:** ✅ Phase 1.1 Complete  
**Next:** Phase 1.2 - FAISS Integration
