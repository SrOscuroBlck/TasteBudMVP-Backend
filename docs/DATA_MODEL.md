# TasteBud Backend -- Data Model

All models use SQLModel (SQLAlchemy under the hood) and are defined in the `models/` directory. JSON columns store vectors, lists, and dictionaries as JSONB in PostgreSQL. The pgvector extension provides the `Vector` column type for embedding storage.

---

## Entity Relationship Overview

```
User
 |-- 1:1 -- BayesianTasteProfile
 |-- 1:1 -- UserScoringWeights
 |-- 1:N -- OnboardingAnswer
 |-- 1:N -- OnboardingState
 |-- 1:N -- UserSession (auth sessions)
 |-- 1:N -- OTPCode
 |-- 1:N -- Interaction
 |-- 1:N -- Rating
 |-- 1:N -- RecommendationSession
 |-- 1:N -- UserOrderHistory
 |-- 1:N -- UserItemInteractionHistory

Restaurant
 |-- 1:N -- MenuItem

RecommendationSession
 |-- 1:N -- RecommendationFeedback
 |-- 1:1 -- PostMealFeedback
 |-- N:1 -- Restaurant

MenuItem
 |-- referenced by -- Rating, Interaction, RecommendationFeedback, UserOrderHistory, UserItemInteractionHistory
```

---

## User

Defined in `models/user.py`. Central entity representing an app user with their taste profile.

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| email | string (unique, indexed) | User email address |
| email_verified | bool | Whether email has been verified |
| created_at | datetime | Account creation timestamp |
| last_updated | datetime | Last profile update |
| last_login | datetime (nullable) | Last login timestamp |
| onboarding_completed | bool | Whether onboarding flow finished |
| allergies | JSON list[str] | User-declared allergies |
| dietary_rules | JSON list[str] | e.g. "vegetarian", "halal" |
| disliked_ingredients | JSON list[str] | Ingredients user dislikes |
| liked_ingredients | JSON list[str] | Ingredients user likes |
| taste_vector | JSON dict[str, float] | 7D taste preferences (sweet, sour, salty, bitter, umami, fatty, spicy) |
| taste_uncertainty | JSON dict[str, float] | Per-axis uncertainty (higher = less certain) |
| taste_archetype_id | UUID (nullable, indexed) | Assigned taste archetype |
| cuisine_affinity | JSON dict[str, float] | Per-cuisine preference scores |
| ingredient_penalties | JSON dict[str, float] | Learned negative weights for specific ingredients |
| permanently_excluded_items | JSON list[str] | Item IDs permanently rejected |
| onboarding_state | JSON dict (nullable) | Current onboarding progress snapshot |

### Taste Vector Axes

The taste vector has 7 dimensions, each in [0, 1]:

| Axis | Meaning |
|---|---|
| sweet | Preference for sweet flavors |
| sour | Preference for sour/acidic flavors |
| salty | Preference for salty flavors |
| bitter | Preference for bitter flavors (coffee, dark chocolate) |
| umami | Preference for savory/umami flavors |
| fatty | Preference for rich, fatty foods |
| spicy | Preference for spicy/hot foods |

---

## BayesianTasteProfile

Defined in `models/bayesian_profile.py`. Beta distribution parameters for each taste axis, used for Thompson Sampling.

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| user_id | UUID (unique, indexed) | FK to User |
| alpha_params | JSON dict[str, float] | Beta distribution alpha per axis |
| beta_params | JSON dict[str, float] | Beta distribution beta per axis |
| mean_preferences | JSON dict[str, float] | Cached posterior means |
| uncertainties | JSON dict[str, float] | Cached posterior uncertainties |
| cuisine_alpha | JSON dict[str, float] | Cuisine preference alpha params |
| cuisine_beta | JSON dict[str, float] | Cuisine preference beta params |
| cuisine_means | JSON dict[str, float] | Cached cuisine preference means |
| last_updated | datetime | Last update timestamp |
| created_at | datetime | Creation timestamp |

Key methods:
- `sample_taste_preferences()` -- draw from Beta posteriors (Thompson Sampling)
- `get_cuisine_preference(cuisine)` -- get mean preference for a cuisine
- `update_cached_statistics()` -- recalculate means and uncertainties from alpha/beta

---

## MenuItem

Defined in `models/restaurant.py`. A single dish on a restaurant's menu.

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| restaurant_id | UUID (indexed) | FK to Restaurant |
| name | string | Dish name |
| description | string | Dish description |
| ingredients | JSON list[str] | Ingredient list |
| allergens | JSON list[str] | Allergen tags |
| dietary_tags | JSON list[str] | e.g. "vegetarian", "gluten-free" |
| cuisine | JSON list[str] | Cuisine classifications |
| price | float (nullable) | Price |
| spice_level | int (nullable) | Spice level (1-5) |
| cooking_method | string (nullable) | e.g. "grilled", "fried" |
| course | string (nullable) | e.g. "appetizer", "main", "dessert" |
| features | JSON dict[str, float] | 7D taste vector for this item |
| texture | JSON dict[str, float] | 3D texture vector (crunchy, creamy, chewy) |
| richness | float (nullable) | Richness score [0, 1] |
| provenance | JSON dict | Origin metadata for inferred attributes |
| inference_confidence | float | Confidence in GPT-inferred attributes (1.0 = fully deterministic) |
| embedding | Vector(1536) (nullable) | OpenAI text embedding |
| reduced_embedding | Vector(64) (nullable) | UMAP-reduced embedding for FAISS |
| embedding_model | string (nullable) | Model used for embedding |
| embedding_version | string (nullable) | Embedding version |
| last_embedded_at | datetime (nullable) | When embedding was generated |

---

## Restaurant

Defined in `models/restaurant.py`.

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| name | string | Restaurant name |
| location | string (nullable) | Location description |
| tags | JSON list[str] | Tags (e.g. "italian", "casual") |

---

## RecommendationSession

Defined in `models/session.py`. Represents a single recommendation interaction at a restaurant.

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| user_id | UUID (indexed) | FK to User |
| restaurant_id | UUID (indexed) | FK to Restaurant |
| meal_intent | string | One of: FULL_MEAL, MAIN_ONLY, APPETIZER_ONLY, DESSERT_ONLY, BEVERAGE_ONLY, LIGHT_SNACK |
| hunger_level | string | Default: "moderate" |
| time_of_day | string | Detected time context |
| detected_hour | int | Hour of day (0-23) |
| day_of_week | int | Day of week (0-6) |
| budget | float (nullable) | Budget constraint |
| party_size | int | Default: 1 |
| time_constraint_minutes | int (nullable) | Time constraint |
| mood | string (nullable) | User mood context |
| occasion | string (nullable) | e.g. "date", "business" |
| dietary_notes | string (nullable) | Session-specific dietary notes |
| started_at | datetime | Session start |
| completed_at | datetime (nullable) | Session completion |
| selected_items | JSON list[str] | Items selected by user |
| status | string | "active", "completed", "abandoned" |
| items_shown | JSON list[str] | All item IDs shown during session |
| excluded_items | JSON list[str] | Items explicitly excluded |
| iteration_count | int | Number of "next" requests |
| active_composition_id | string (nullable) | Current meal composition ID |
| composition_validation_state | JSON dict | Meal composition feedback state |
| user_experience_level | string | "learning" or "experienced" |
| context_snapshot | JSON dict | Captured context at session start |
| email_scheduled_at | datetime (nullable) | Feedback email scheduled time |
| email_sent_at | datetime (nullable) | Feedback email sent time |

---

## Feedback Models

### RecommendationFeedback

In-session feedback on a specific recommended item.

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| session_id | UUID (indexed) | FK to RecommendationSession |
| item_id | UUID (indexed) | FK to MenuItem |
| feedback_type | string | LIKE, DISLIKE, SAVE_FOR_LATER, SELECTED, ACCEPTED, SKIP, MORE |
| comment | string (nullable) | Optional user comment |
| timestamp | datetime | When feedback was given |

### PostMealFeedback

Submitted after the meal is over. One per session.

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| session_id | UUID (indexed) | FK to RecommendationSession |
| items_ordered | JSON list[UUID] | Items actually ordered |
| overall_satisfaction | int | 1-5 scale |
| would_order_again | bool | Repeat intent |
| taste_match | int | 1-5 scale, how well taste matched |
| portion_size_rating | int (nullable) | 1-5 scale |
| value_for_money | int (nullable) | 1-5 scale |
| service_quality | int (nullable) | 1-5 scale |
| wait_time_minutes | int (nullable) | Actual wait time |
| additional_notes | string (nullable) | Free text |
| submitted_at | datetime | Submission timestamp |

### Rating

Standalone item rating (outside session context).

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| user_id | UUID (indexed) | FK to User |
| item_id | UUID (indexed) | FK to MenuItem |
| rating | int | 1-5 scale |
| liked | bool | Binary like/dislike |
| reasons | string | Reason text |
| comment | string | Optional comment |
| timestamp | datetime | When rated |

### Interaction

Lightweight event tracking (views, clicks, dismissals).

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| user_id | UUID (indexed) | FK to User |
| item_id | UUID (indexed) | FK to MenuItem |
| type | string | "view", "click", "dismiss", "purchase" |
| timestamp | datetime | Event timestamp |

---

## User History Models

### UserOrderHistory

Tracks what users have ordered, including whether the item was recommended and whether they enjoyed it.

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| user_id | UUID (indexed) | FK to User |
| restaurant_id | UUID (indexed) | FK to Restaurant |
| item_id | UUID (indexed) | FK to MenuItem |
| ordered_at | datetime | Order timestamp |
| session_id | UUID (nullable) | FK to RecommendationSession |
| was_recommended | bool | Whether TasteBud recommended it |
| enjoyed | bool (nullable) | Whether user enjoyed it |
| rating | int (nullable) | 1-5 rating |
| repeat_count | int | How many times ordered (default: 1) |

### UserItemInteractionHistory

Aggregated interaction tracking per user-item pair.

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| user_id | UUID (indexed) | FK to User |
| item_id | UUID (indexed) | FK to MenuItem |
| first_shown_at | datetime | First time item was shown |
| last_shown_at | datetime | Most recent showing |
| times_shown | int | Total show count |
| was_dismissed | bool | Ever dismissed |
| was_disliked | bool | Ever disliked |
| was_liked | bool | Ever liked |
| was_ordered | bool | Ever ordered |
| session_ids | JSON list[str] | Sessions where shown |

---

## Auth Models

### UserSession

Authentication session (not to be confused with RecommendationSession).

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| user_id | UUID (indexed) | FK to User |
| token | string (unique, indexed) | Access token |
| refresh_token | string (unique, indexed) | Refresh token |
| created_at | datetime | Session creation |
| expires_at | datetime | Token expiry |
| last_used_at | datetime | Last API call |
| device_info | string (nullable) | Client device info |
| ip_address | string (nullable) | Client IP |
| user_agent | string (nullable) | Client user agent |
| is_active | bool | Whether session is active |

### OTPCode

One-time password for email-based authentication.

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| user_id | UUID (indexed) | FK to User |
| code | string (indexed) | OTP code |
| created_at | datetime | Generation timestamp |
| expires_at | datetime | Expiry timestamp |
| used_at | datetime (nullable) | When it was used |
| is_used | bool | Whether it was consumed |
| attempts | int | Failed verification attempts |
| max_attempts | int | Maximum allowed attempts (default: 3) |

---

## Population and Archetype Models

### PopulationStats

Global population-level statistics used as priors for new users.

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| axis_prior_mean | JSON dict[str, float] | Population mean per taste axis |
| axis_prior_sigma | JSON dict[str, float] | Population std dev per taste axis |
| cuisine_prior | JSON dict[str, float] | Population cuisine preferences |
| item_popularity_global | JSON dict[str, float] | Global item popularity scores |
| item_popularity_by_restaurant | JSON dict[str, float] | Per-restaurant popularity |
| decay_half_life_days | int | Popularity decay half-life (default: 30) |

### TasteArchetype

Predefined taste profile clusters for cold-start.

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| name | string (indexed) | Archetype name |
| description | string | Human-readable description |
| taste_vector | JSON dict[str, float] | Representative taste vector |
| typical_cuisines | JSON list[str] | Commonly associated cuisines |
| example_items | JSON list[str] | Example dish names |

---

## Scoring and Query Models

### UserScoringWeights

Per-user learned weights for the recommendation scoring formula.

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| user_id | UUID (unique, indexed) | FK to User |
| taste_weight | float | Weight for taste similarity (default: 0.5) |
| cuisine_weight | float | Weight for cuisine affinity (default: 0.2) |
| popularity_weight | float | Weight for item popularity (default: 0.15) |
| exploration_weight | float | Weight for exploration term (default: 0.15) |
| learning_rate | float | Online learning rate (default: 0.01) |
| momentum | JSON dict[str, float] | Gradient momentum for weight updates |
| feedback_count | int | Number of feedback signals processed |
| last_calibration_at | datetime (nullable) | Last weight calibration |

### QueryModifier

Enum of natural language modifiers: SPICIER, LESS_SPICY, SWEETER, LESS_SWEET, SALTIER, LESS_SALTY, RICHER, LIGHTER, CRUNCHIER, CREAMIER, MORE_SAVORY, VEGETARIAN, HEALTHIER.

### ParsedQuery

Structured representation of a parsed natural language recommendation query, containing intent, modifiers, filters, and taste adjustments.

---

## Ingestion Models

### MenuUpload

Tracks a menu upload (PDF or image) through its processing lifecycle.

| Column | Type | Description |
|---|---|---|
| id | UUID (PK) | Auto-generated |
| restaurant_id | UUID (indexed) | FK to Restaurant |
| source_type | IngestionSource enum | PDF, IMAGE, or URL |
| status | IngestionStatus enum | PENDING, PROCESSING, COMPLETED, FAILED, REVIEW_REQUIRED |
| file_path | string (nullable) | Path to uploaded file |
| original_filename | string (nullable) | Original file name |
| extracted_text | string (nullable) | Raw extracted text |
| parsed_data | JSON dict | Parsed menu structure |
| items_created | int | Successfully created items |
| items_failed | int | Failed item creations |
| error_message | string (nullable) | Error details if failed |
| processing_time_seconds | float (nullable) | Processing duration |
| created_at | datetime | Upload timestamp |
| updated_at | datetime | Last status update |

---

## Evaluation Models

Used for offline evaluation and A/B testing.

### EvaluationMetric

Stores individual evaluation metric values for offline analysis (precision, recall, NDCG, etc.).

### OfflineEvaluation

Records results of offline evaluation runs.

### OnlineEvaluationMetrics

Tracks online metrics aggregated over time periods.

### ABTestExperiment

Configuration for A/B test experiments.

### InterleavingResult

Records results of team-draft interleaving experiments between algorithm variants.
