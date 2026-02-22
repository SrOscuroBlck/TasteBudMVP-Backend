# Changelog

All notable changes to the TasteBud recommendation system.

---

## [Reorganization] - 2026-02-15

### Changed - Codebase Reorganization

#### Service Domain Structure
- Reorganized 40+ flat service files under `services/` into 13 domain packages:
  - `core/` -- RecommendationService, RetrievalService, RerankingService, SessionService
  - `features/` -- FAISSService, EmbeddingService, features, gpt_helper, llm_features
  - `learning/` -- BayesianProfileService, UnifiedFeedbackService, InSessionLearningService, OnlineLearningService, WeightLearningService
  - `composition/` -- MealCompositionService, HarmonyService, QueryParsingService
  - `diversity/` -- MMRService, CrossEncoderService
  - `user/` -- AuthService, OnboardingService, InteractionHistoryService, ArchetypeService
  - `ingestion/` -- IngestionOrchestrator, PDFProcessor, MenuParser
  - `explanation/` -- ExplanationService, ExplanationEnhancementService, PersonalizedExplanationService
  - `context/` -- ContextEnhancementService, MenuService
  - `evaluation/` -- ConfidenceService, EvaluationMetricsService, TeamDraftInterleavingService
  - `ml/` -- MLRerankingService, UMAPReducer
  - `infrastructure/` -- IndexMaintenanceService, ScheduledMaintenance, SimilarityMatrixService
  - `communication/` -- EmailService, EmailFollowupService, RatingReminderService
- Each domain package has an `__init__.py` with proper exports
- Updated all imports across 45 files (routes, services, scripts, main.py)

#### Script Organization
- Organized scripts into subdirectories:
  - `scripts/migrations/` -- 7 schema migration scripts
  - `scripts/data_generation/` -- FAISS index, similarity matrix, embeddings, archetype clustering
  - `scripts/maintenance/` -- taste vector regeneration
  - `scripts/admin/` -- user reset, config validation
- Removed 19 unused scripts (test utilities, one-off debugging, evaluation scripts)

#### Cleanup
- Moved integration test scripts to `tests/`
- Removed stale root files (test artifacts, old databases, logs)
- Cleared `__pycache__` directories

#### Documentation
- Replaced 12 outdated plan/fix documents in `docs/` with developer-facing documentation:
  - `ARCHITECTURE.md` -- system architecture, service domains, request flows
  - `API_REFERENCE.md` -- complete endpoint reference with request/response examples
  - `DATA_MODEL.md` -- database models, relationships, column definitions
  - `DEVELOPER_GUIDE.md` -- setup, running, testing, extending, troubleshooting
  - `RECOMMENDATION_PIPELINE.md` -- algorithm explanation with math formulas
- Rewrote `README.md` as a concise entry point linking to detailed docs

---

## [Phase 5] - 2026-02-01

### Added - Infrastructure and Observability

#### Index Maintenance
- **IndexMaintenanceService** (`services/infrastructure/index_maintenance_service.py`)
  - Full FAISS index rebuild with embedding generation
  - Build statistics reporting (duration, item count, dimension)
- **ScheduledIndexMaintenance** (`services/infrastructure/scheduled_maintenance.py`)
  - Async background task for periodic FAISS index rebuilds
  - Configurable interval (default: 24 hours)
- **SimilarityMatrixService** (`services/infrastructure/similarity_matrix_service.py`)
  - Pre-computed pairwise similarity matrix for MMR diversity
  - Used by MMRService to avoid recomputing similarities at query time

#### Admin Rebuild Endpoints
- `POST /api/v1/admin/rebuild/faiss-64d` -- trigger 64D FAISS index rebuild
- `POST /api/v1/admin/rebuild/faiss-1536d` -- trigger 1536D FAISS index rebuild
- `POST /api/v1/admin/rebuild/similarity-matrix` -- trigger similarity matrix rebuild
- `POST /api/v1/admin/rebuild/all` -- trigger all rebuilds
- `GET /api/v1/admin/rebuild/status` -- check rebuild progress

#### Communication
- **EmailService** (`services/communication/email_service.py`)
  - HTML/plain-text email delivery via SMTP
  - Post-meal feedback collection emails
- **EmailFollowupService** (`services/communication/email_followup_service.py`)
  - Automated follow-up scheduling after session completion
- **RatingReminderService** (`services/communication/rating_reminder_service.py`)
  - Reminder emails for pending post-meal feedback

#### Observability
- Circuit breaker pattern for external service calls (`utils/circuit_breaker.py`)
- Prometheus metrics collection (`utils/prometheus_metrics.py`)
- Request timing decorators (`utils/timing.py`)
- Correlation ID propagation (`utils/correlation_id.py`)
- Configurable log levels and request timing logging

---

## [Phase 4] - 2026-01-25

### Added - Explanations and Evaluation

#### Explanation Service
- **ExplanationService** (`services/explanation/explanation_service.py`)
  - Template-based recommendation explanations across 7 types: taste match, dietary fit, budget, mood, discovery, popularity, time-appropriate
  - LLM-first approach with template fallback
- **PersonalizedExplanationService** (`services/explanation/personalized_explanation_service.py`)
  - GPT-powered explanations using user history (recent likes, dislikes, orders, favorite cuisines)
- **ExplanationEnhancementService** (`services/explanation/explanation_enhancement_service.py`)
  - Contextual enhancement of explanations (time, occasion, past orders)

#### Evaluation Framework
- **ConfidenceService** (`services/evaluation/confidence_service.py`)
  - Per-recommendation confidence scores (0.0-1.0) based on profile certainty, item feature completeness, rating history, and context match
- **EvaluationMetricsService** (`services/evaluation/evaluation_metrics_service.py`)
  - Offline metrics: NDCG@k, diversity, coverage
  - Online metrics aggregated over configurable time periods
  - Persistent metric storage
- **TeamDraftInterleavingService** (`services/evaluation/team_draft_interleaving_service.py`)
  - A/B testing via team-draft interleaving
  - Merges two algorithm outputs into a single ranked list
  - Statistical comparison using scipy.stats

#### Models
- `EvaluationMetric`, `OfflineEvaluation`, `OnlineEvaluationMetrics` -- metric storage
- `ABTestExperiment`, `InterleavingResult` -- A/B test configuration and results

---

## [Phase 3] - 2026-01-18

### Added - Sessions, Composition, Diversity, and Feedback Learning

#### Recommendation Sessions
- **RecommendationSessionService** (`services/core/session_service.py`)
  - Session lifecycle: start, iterate (next batch), record feedback, complete, abandon
  - Tracks shown items, excluded items, iteration count
  - Visit history detection (repeat visitor context)
  - Meal intent support: FULL_MEAL, MAIN_ONLY, APPETIZER_ONLY, DESSERT_ONLY, BEVERAGE_ONLY, LIGHT_SNACK

#### Session API
- `POST /api/v1/sessions/start` -- start session with restaurant, meal intent, budget, constraints
- `POST /api/v1/sessions/{id}/next` -- get next batch of recommendations
- `POST /api/v1/sessions/{id}/feedback` -- in-session item feedback (like, dislike, skip, select)
- `POST /api/v1/sessions/{id}/composition/feedback` -- per-course meal composition feedback
- `POST /api/v1/sessions/{id}/complete` -- complete session with selected items
- `POST /api/v1/sessions/{id}/abandon` -- abandon active session
- `GET /api/v1/sessions/restaurant/{id}/history` -- visit history at a restaurant

#### Post-Meal Feedback
- `GET /api/v1/feedback/pending` -- list sessions awaiting feedback
- `POST /api/v1/feedback/post-meal` -- submit satisfaction, taste match, value ratings
- `GET /api/v1/feedback/submit/{token}` -- email-token feedback form (no auth)
- `POST /api/v1/feedback/submit/{token}` -- submit via email token (no auth)

#### Meal Composition
- **MealCompositionService** (`services/composition/meal_composition_service.py`)
  - Multi-course meal assembly (appetizer + main + dessert)
  - Flavor harmony scoring between courses
  - Budget and time constraint enforcement
  - Per-course feedback with partial accept/reject
- **HarmonyService** (`services/composition/harmony_service.py`)
  - Taste contrast, texture variety, cuisine coherence scoring

#### Query-Based Recommendations
- **QueryParsingService** (`services/composition/query_service.py`)
  - Natural language query parsing into structured `ParsedQuery`
  - Intent detection: SIMILAR_TO, EXPLORE_CUISINE, MOOD_BASED, FREE_TEXT
  - Taste modifiers: spicier, sweeter, lighter, crunchier, etc.
- **CrossEncoderService** (`services/diversity/cross_encoder_service.py`)
  - Fine-grained query-item relevance scoring using ms-marco-MiniLM-L-6-v2

#### MMR Diversity
- **MMRService** (`services/diversity/mmr_service.py`)
  - Maximal Marginal Relevance reranking balancing relevance vs. diversity
  - Configurable alpha parameter (default: 0.7)
  - Diversity constraints: per-cuisine caps, price range limits

#### Feedback Learning
- **BayesianProfileService** (`services/learning/bayesian_profile_service.py`)
  - Beta distribution taste profiles with Thompson Sampling
  - Posterior updates from feedback (like/dislike/rating/order)
  - Cuisine-level Bayesian preferences
- **UnifiedFeedbackService** (`services/learning/unified_feedback_service.py`)
  - Processes all feedback types with temporal decay weighting (half-life: 21 days)
  - Configurable learning rates: mild (quick-like), medium (like/dislike), strong (rating)
- **InSessionLearningService** (`services/learning/in_session_learning_service.py`)
  - Real-time taste adjustments within a single session
  - Ephemeral adjustments that influence remaining recommendations
- **WeightLearningService** (`services/learning/weight_learning_service.py`)
  - Per-user scoring weight optimization via online gradient updates
  - Learns relative importance of taste, cuisine, popularity, and exploration components
- **OnlineLearningService** (`services/learning/online_learning_service.py`)
  - Cross-session online learning updates

#### Context Enhancement
- **ContextEnhancementService** (`services/context/context_enhancement_service.py`)
  - Time-of-day hard filters (breakfast items in morning, no breakfast at dinner)
  - Occasion and mood-based scoring adjustments

#### Models
- `RecommendationSession` -- session state with context snapshot, shown/excluded items
- `RecommendationFeedback` -- in-session per-item feedback
- `PostMealFeedback` -- post-meal satisfaction ratings
- `UserOrderHistory` -- order tracking with repeat detection
- `UserItemInteractionHistory` -- aggregated per-user-item interaction tracking
- `UserScoringWeights` -- per-user learned scoring weights
- `BayesianTasteProfile` -- Beta distribution parameters per taste axis
- `QueryModifier`, `ParsedQuery` -- structured query representation
- `MealIntent`, `FeedbackType` enums

---

## [Phase 2] - 2026-01-10

### Added - Retrieval and Reranking Pipeline

#### Retrieval Service
- **RetrievalService** (`services/core/retrieval_service.py`)
  - FAISS approximate nearest-neighbor candidate retrieval
  - SQL fallback when FAISS index is unavailable
  - Hard safety filters: allergen removal, dietary rule enforcement
  - Configurable candidate pool multiplier (3x requested count)

#### Reranking Service
- **RerankingService** (`services/core/reranking_service.py`)
  - Composite scoring: taste cosine similarity + cuisine affinity + popularity + exploration
  - Time-of-day contextual adjustments
  - GPT confidence discount for inferred item attributes
  - Ingredient penalty application from cross-restaurant feedback
  - Population-level prior incorporation for cold-start users

#### ML Reranking
- **MLRerankingService** (`services/ml/ml_reranking_service.py`)
  - LightGBM-based reranking with user-item-context feature extraction
  - Rule-based fallback when model is unavailable
  - Pluggable stage in the recommendation pipeline

#### Recommendation Orchestrator
- **RecommendationService** (`services/core/recommendation_service.py`)
  - Central orchestrator wiring the full pipeline: retrieval, reranking, MMR, composition, explanation
  - Entry points: `recommend()` and `recommend_with_session()`

#### Search Endpoint
- `GET /api/v1/search` -- search/filter menu items by text, cuisine, dietary tags, price range

---

## [Phase 1.2] - 2026-01-04

### Added - Fast Similarity Search with FAISS

#### FAISSService
- **FAISSService** (`services/features/faiss_service.py`)
  - Fast k-nearest neighbor search using FAISS IndexFlatIP
  - Build index from embeddings with automatic vector normalization
  - Persistent storage to `data/faiss_indexes/` directory
  - Support for both 64D (reduced) and 1536D (full) embeddings
  - Index metadata tracking (dimension, count, build timestamp, version)
  - UUID mapping for MenuItem ID preservation

#### Similar Items API
- `GET /api/v1/items/{item_id}/similar` -- FAISS-powered similarity search
  - Filters: cuisine, max_price, dietary tags
  - Optional GPT-powered similarity explanations
  - Post-filtering: retrieves k*3 candidates, applies filters, returns top k

#### Application Lifecycle
- FAISS index loaded once at startup into app.state
- Fallback from 64D to 1536D if reduced embeddings not available
- Graceful degradation when index is not built

#### Scripts
- `build_faiss_index.py` -- build FAISS index from database embeddings
  - Support for both 64D and 1536D dimensions
  - Docker container execution support

---

## [Phase 1.1.1] - 2026-01-04

### Changed - LLM Configuration

- Updated to GPT-5 nano (`gpt-5-mini`) as primary model
  - $0.05 input / $0.40 output per 1M tokens
  - 400K context window, 128K max output tokens
- Fallback to GPT-4.1 nano (`gpt-4.1-nano`) when GPT-5 unavailable

---

## [Phase 1.1] - 2025-11-05

### Added - Infrastructure and Foundation

#### Docker and Database
- PostgreSQL 16 with pgvector extension for vector similarity search
- Redis 7 for caching layer
- Docker Compose orchestration with health checks
- API container with FastAPI and auto-reload
- Database auto-sync with SQLModel

#### Vector Embeddings
- **EmbeddingService** (`services/features/embedding_service.py`)
  - OpenAI text-embedding-3-small (1536 dimensions) as primary
  - sentence-transformers all-MiniLM-L6-v2 as local fallback
  - True batch processing (single API call per batch)

#### Dimensionality Reduction
- **UMAPReducer** (`services/ml/umap_reducer.py`)
  - Reduces 1536 dims to 64 dims for FAISS efficiency
  - Cosine metric, model persistence with joblib

#### Database Schema
- `MenuItem` vector columns: `embedding` (Vector 1536), `reduced_embedding` (Vector 64)
- Embedding metadata: `embedding_model`, `embedding_version`, `last_embedded_at`
- pgvector extension auto-enabled on startup

#### Scripts
- `generate_embeddings.py` -- batch embed all MenuItems
- `build_similarity_matrix.py` -- pre-compute pairwise similarities
- `cluster_taste_archetypes.py` -- generate taste archetype clusters

#### Utilities
- Structured JSON logging with correlation ID support
- Culinary domain rules (flavor pairings, course ordering)
- File upload handling for menu PDFs

### Core Models
- `User` -- taste vector (7D), texture (3D), richness, preferences, allergens, dietary rules
- `Restaurant`, `MenuItem` -- menu data with feature vectors and provenance tracking
- `Rating`, `Interaction` -- feedback and event tracking
- `PopulationStats`, `TasteArchetype` -- population-level priors and archetype clustering
- `UserSession`, `OTPCode` -- email OTP authentication
- `MenuUpload`, `ParsedMenuItem` -- PDF ingestion pipeline models
- `OnboardingState`, `OnboardingQuestion`, `OnboardingAnswer` -- onboarding flow state

### Core Services
- **OnboardingService** -- "Would You Rather?" pairwise questions targeting highest-uncertainty axes
- **AuthService** -- email OTP authentication with token management
- **IngestionOrchestrator** -- PDF upload, text extraction (pdfplumber + Tesseract), GPT parsing
- **features.py** -- pure functions: cosine similarity, allergen checks, diet rule enforcement
- **gpt_helper.py** -- GPT wrapper with fallback for onboarding questions and taste inference
