# TasteBud Backend

FastAPI backend for food recommendations. Built next to the HR backend, reusing its conventions (FastAPI + SQLModel + service layer). It delivers onboarding, safe/deterministic recommendations, feedback learning, and bounded GPT usage.

## Features
- Onboarding via “Would You Rather?” questions with early stop and uncertainty targeting
- Deterministic safety: hard allergy/diet filters independent from GPT
- Scoring with cosine similarity + cuisine affinity + popularity; MMR diversification
- GPT used only for: onboarding question JSON, recommendation rationale text, and ingredient/tag inference. All GPT outputs are validated and optional
- Persistence for users, menus, interactions, ratings, and priors

## Getting started

### Prereqs
- Python 3.10+
- Optional: Docker (for DB only)

### Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `.env` in the project root (see `.env.example`):
```
TASTEBUD_DATABASE_URL=sqlite:///./tastebud.db
OPENAI_API_KEY=sk-... # optional; required to exercise GPT-assisted features
OPENAI_MODEL=gpt-4o-mini
HOST=0.0.0.0
PORT=8010
DEBUG=true
ALLOWED_ORIGINS=*
```

Run the API:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8010
```

Seed sample data (optional):
```bash
python data/seed.py
```

Smoke test (optional, requires server running):
```bash
python scripts/smoke_gpt_flow.py
```

### Postgres via Docker (DB only)
Use the provided `docker-compose.yml` to run Postgres. Then set `TASTEBUD_DATABASE_URL` accordingly (e.g., `postgresql+psycopg2://postgres:postgres@localhost:5432/tastebud`). The app itself is not containerized.

## API Reference

All endpoints are prefixed with `/api/v1`.

### Health
- GET `/health`
	- 200: `{ "status": "ok", "version": "0.1.0" }`

### Onboarding
- POST `/onboarding/start`
	- Body: `{ "user_id": "<uuid>" }`
	- Creates the user if not exists, initializes priors, and returns the first question.
	- 200: `{ question_id, prompt, options: [{id,label,tags,ingredient_keys}], axis_hints }`

- POST `/onboarding/answer`
	- Body: `{ "user_id": "<uuid>", "question_id": "<uuid|string>", "chosen_option_id": "A|B" }`
	- Updates the user taste vector and uncertainty; may early-stop.
	- 200: Either `{ "complete": true }` or the next question object as above.

- GET `/onboarding/state?user_id=<uuid>`
	- 200: `{ state_id, active, confidence, ... }` or `{}`

### Users
- GET `/users/{user_id}/profile`
	- 200: `{ id, allergies, dietary_rules, liked_ingredients, disliked_ingredients, taste_vector, taste_uncertainty, cuisine_affinity }`

- PATCH `/users/{user_id}/preferences`
	- Body (partial): `{ allergies?: string[], dietary_rules?: string[], liked_ingredients?: string[], disliked_ingredients?: string[] }`
	- 200: `{ status: "ok" }`

### Restaurants & Menus
- POST `/restaurants`
	- Body: `{ name: string, location?: string, tags?: string[] }`
	- 200: `{ id, name }`

- POST `/restaurants/{restaurant_id}/menu/ingest`
	- Body: `[{ name, description?, ingredients?: string[], allergens?: string[], dietary_tags?: string[], cuisine?: string[], price?: number, tags?: string[] }]`
	- Ingests items and computes features deterministically.
	- 200: `{ count: number }`

- POST `/restaurants/{restaurant_id}/menu/infer`
	- Body: `{ name: string, description?: string }`
	- GPT-assisted inference of ingredients/tags with provenance and confidence.
	- 200: `{ candidates: [{ingredient, confidence}], tags: string[], axis_hints: object, confidence: number }`

- GET `/restaurants/{restaurant_id}/menu`
	- 200: `[{ id, name, price, dietary_tags }]`

### Recommendations
- GET `/recommendations?user_id=<uuid>&restaurant_id=<uuid>&top_n=10&budget=<float>&time_of_day=<str>`
	- Returns top items after hard safety filters and scoring with diversification.
	- 200: `{ items: [{ item_id, name, score, matched_axes, reason, safety_flags, cuisine, price, confidence, provenance }] }`

### Feedback
- POST `/feedback/rating`
	- Body: `{ user_id: uuid, item_id: uuid, rating: int(1-5), liked: bool, reasons?: string[], comment?: string }`
	- 200: `{ id }`

- POST `/feedback/interaction`
	- Body: `{ user_id: uuid, item_id: uuid, type: "view" | "click" | "dismiss" | "purchase" }`
	- 200: `{ id }`

- POST `/discovery/quick-like`
	- Body: `{ user_id: uuid, item_id: uuid, liked?: bool }`
	- Applies a small learning nudge.
	- 200: `{ status: "ok" }`

## Design Notes
- Safety: `services/features.py` implements allergen checks and diet rules; not influenced by GPT.
- GPT usage: `services/gpt_helper.py` wraps calls; failures fall back to deterministic flows.
- Onboarding: Uses priors from `PopulationStats`, targets axes with highest uncertainty, and early-stops by confidence.
- Recommendations: Cosine similarity + weights; MMR for diversity; GPT reason is optional.
- Persistence: SQLModel models in `models/*` with JSON columns for vectors and preferences.

## Troubleshooting
- If onboarding 500s, check `.env` and the `OPENAI_*` vars. The service falls back when GPT is unavailable.
- SQLite is default; for Postgres ensure the URL is correct and the DB is reachable.
- For CORS, set `ALLOWED_ORIGINS` (comma-separated) in `.env`.

## License
Internal project scaffold for demonstration purposes.