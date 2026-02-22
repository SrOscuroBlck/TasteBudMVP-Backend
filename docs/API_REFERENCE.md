# TasteBud Backend -- API Reference

All endpoints are mounted under the `/api/v1` prefix. Authentication uses Bearer tokens obtained through the OTP flow.

---

## Root

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | No | Application health check. Returns `{app, status}`. |

---

## Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/request-otp` | No | Send a one-time password to user email. |
| POST | `/api/v1/auth/verify-otp` | No | Verify OTP and receive access/refresh tokens. |
| POST | `/api/v1/auth/refresh-token` | No | Exchange a refresh token for a new access token. |
| GET | `/api/v1/auth/session` | Yes | Get current authenticated user info. |
| POST | `/api/v1/auth/logout` | Yes | Invalidate the current session token. |

### POST /api/v1/auth/request-otp

Request body:
```json
{ "email": "user@example.com" }
```

Response:
```json
{ "success": true, "message": "OTP sent", "expires_at": "2025-01-01T00:10:00Z" }
```

### POST /api/v1/auth/verify-otp

Request body:
```json
{ "email": "user@example.com", "code": "123456", "device_info": "optional" }
```

Response:
```json
{
  "success": true,
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_at": "2025-01-01T01:00:00Z",
  "user": { "id": "uuid", "email": "...", "onboarding_completed": false }
}
```

---

## Onboarding

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/onboarding/start` | Yes | Start onboarding flow for authenticated user. |
| POST | `/api/v1/onboarding/answer` | Yes | Submit answer to current onboarding question. |
| GET | `/api/v1/onboarding/state` | Yes | Get current onboarding progress. |

### POST /api/v1/onboarding/start

Returns the first "Would You Rather?" question:
```json
{
  "question_id": "uuid",
  "prompt": "Would you rather have...",
  "options": [
    { "id": "A", "label": "A rich chocolate cake", "tags": ["sweet", "rich"], "ingredient_keys": ["chocolate"] },
    { "id": "B", "label": "A tangy lemon sorbet", "tags": ["sour", "light"], "ingredient_keys": ["lemon"] }
  ],
  "axis_hints": { "sweet": 0.8, "sour": 0.2 }
}
```

### POST /api/v1/onboarding/answer

Request body:
```json
{ "question_id": "uuid", "chosen_option_id": "A" }
```

Response: either the next question (same format as above) or `{ "complete": true }` when the profile has converged (confidence >= 0.8 or 7 questions answered).

---

## User Profile

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/users/{user_id}/profile` | Yes | Get user's taste profile and preferences. |
| PATCH | `/api/v1/users/{user_id}/preferences` | Yes | Update dietary preferences. |

### GET /api/v1/users/{user_id}/profile

Response:
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "allergies": ["peanuts"],
  "dietary_rules": ["vegetarian"],
  "liked_ingredients": ["basil", "garlic"],
  "disliked_ingredients": ["cilantro"],
  "taste_vector": { "sweet": 0.6, "sour": 0.3, "salty": 0.5, "bitter": 0.2, "umami": 0.7, "fatty": 0.4, "spicy": 0.5 },
  "taste_uncertainty": { "sweet": 0.1, "sour": 0.3, "salty": 0.2, "bitter": 0.4, "umami": 0.1, "fatty": 0.2, "spicy": 0.3 },
  "cuisine_affinity": { "Italian": 0.8, "Japanese": 0.6 },
  "onboarding_completed": true
}
```

### PATCH /api/v1/users/{user_id}/preferences

Request body (all fields optional):
```json
{
  "allergies": ["peanuts", "shellfish"],
  "dietary_rules": ["vegetarian"],
  "liked_ingredients": ["basil"],
  "disliked_ingredients": ["cilantro"]
}
```

---

## Restaurants

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/restaurants` | Yes | Create a new restaurant. |
| GET | `/api/v1/restaurants` | Yes | List all restaurants. |
| GET | `/api/v1/restaurants/{restaurant_id}` | Yes | Get restaurant details with menu summary. |
| GET | `/api/v1/restaurants/{restaurant_id}/menu` | Yes | List all menu items. |
| POST | `/api/v1/restaurants/{restaurant_id}/menu/ingest` | Yes | Bulk ingest menu items. |
| POST | `/api/v1/restaurants/{restaurant_id}/menu/infer` | Yes | Infer item attributes via GPT. |

### POST /api/v1/restaurants

Request body:
```json
{ "name": "Ristorante Roma", "location": "Downtown", "tags": ["italian", "fine-dining"] }
```

### POST /api/v1/restaurants/{restaurant_id}/menu/ingest

Request body (array of items):
```json
[
  {
    "name": "Margherita Pizza",
    "price": 14.99,
    "description": "Classic tomato and mozzarella",
    "ingredients": ["tomato", "mozzarella", "basil"],
    "allergens": ["gluten", "dairy"],
    "dietary_tags": ["vegetarian"],
    "cuisine": ["Italian"]
  }
]
```

Response: `{ "count": 1 }`

---

## Recommendations

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/recommendations` | Yes | Get personalized recommendations (non-session). |
| GET | `/api/v1/items/{item_id}` | Yes | Get full item details. |
| GET | `/api/v1/items/{item_id}/similar` | Yes | Find similar items via FAISS. |
| GET | `/api/v1/search` | Yes | Search/filter menu items. |
| POST | `/api/v1/discovery/quick-like` | Yes | Quick like/dislike for a discovered item. |

### GET /api/v1/recommendations

Query parameters:

| Parameter | Type | Required | Description |
|---|---|---|---|
| `restaurant_id` | UUID | No | Filter to a specific restaurant. |
| `top_n` | int | No | Number of results (default: 10). |
| `budget` | float | No | Maximum price filter. |
| `time_of_day` | string | No | e.g. "lunch", "dinner". |
| `mood` | string | No | e.g. "adventurous", "comfort". |
| `occasion` | string | No | e.g. "date", "business". |
| `course_preference` | string | No | e.g. "main", "appetizer". |

### GET /api/v1/items/{item_id}/similar

Query parameters: `k` (number of results), `cuisine`, `max_price`, `dietary`, `explain` (boolean).

### GET /api/v1/search

Query parameters: `q` (text query), `cuisine`, `dietary`, `max_price`, `min_price`, `restaurant_id`, `limit`.

---

## Sessions

Sessions represent a user's recommendation interaction at a specific restaurant. The flow is: start -> get recommendations (iterate) -> provide feedback -> complete or abandon.

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/sessions/start` | Yes | Start a new recommendation session. |
| GET | `/api/v1/sessions/{session_id}` | Yes | Get session details. |
| POST | `/api/v1/sessions/{session_id}/next` | Yes | Get next batch of recommendations. |
| POST | `/api/v1/sessions/{session_id}/feedback` | Yes | Submit feedback on a recommended item. |
| POST | `/api/v1/sessions/{session_id}/composition/feedback` | Yes | Submit feedback on a meal composition. |
| POST | `/api/v1/sessions/{session_id}/complete` | Yes | Complete session with selected items. |
| POST | `/api/v1/sessions/{session_id}/abandon` | Yes | Abandon an active session. |
| GET | `/api/v1/sessions/restaurant/{restaurant_id}/history` | Yes | Get visit history at a restaurant. |

### POST /api/v1/sessions/start

Request body:
```json
{
  "restaurant_id": "uuid",
  "meal_intent": "FULL_MEAL",
  "budget": 50.00,
  "time_constraint_minutes": 60
}
```

`meal_intent` options: `FULL_MEAL`, `MAIN_ONLY`, `APPETIZER_ONLY`, `DESSERT_ONLY`, `BEVERAGE_ONLY`, `LIGHT_SNACK`.

Response:
```json
{ "session_id": "uuid", "message": "Session started", "visit_context": {...} }
```

### POST /api/v1/sessions/{session_id}/next

Request body:
```json
{ "count": 10 }
```

Returns the next batch of personalized recommendations. Items shown in previous iterations are excluded.

### POST /api/v1/sessions/{session_id}/feedback

Request body:
```json
{ "item_id": "uuid", "feedback_type": "LIKE", "comment": "optional" }
```

`feedback_type` options: `LIKE`, `DISLIKE`, `SAVE_FOR_LATER`, `SELECTED`, `ACCEPTED`, `SKIP`, `MORE`.

### POST /api/v1/sessions/{session_id}/composition/feedback

Used when `meal_intent` is `FULL_MEAL`. Submit per-course feedback on a composed meal suggestion.

Request body:
```json
{
  "composition_id": "uuid",
  "appetizer_feedback": "accept",
  "main_feedback": "accept",
  "dessert_feedback": "reject",
  "composition_action": "partial_accept"
}
```

### POST /api/v1/sessions/{session_id}/complete

Request body:
```json
{ "selected_item_ids": ["uuid1", "uuid2"] }
```

---

## Post-Meal Feedback

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/feedback/pending` | Yes | List sessions awaiting post-meal feedback. |
| POST | `/api/v1/feedback/post-meal` | Yes | Submit post-meal feedback for a completed session. |
| GET | `/api/v1/feedback/submit/{token}` | No | Get feedback form data via email token. |
| POST | `/api/v1/feedback/submit/{token}` | No | Submit feedback via email token. |

### POST /api/v1/feedback/post-meal

Request body:
```json
{
  "session_id": "uuid",
  "items_ordered": ["uuid1", "uuid2"],
  "overall_satisfaction": 4,
  "would_order_again": true,
  "taste_match": 4,
  "portion_size_rating": 3,
  "value_for_money": 4,
  "service_quality": 5,
  "wait_time_minutes": 15,
  "additional_notes": "Great recommendations"
}
```

---

## Ratings and Interactions

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/feedback/rating` | Yes | Submit a detailed rating for a menu item. |
| POST | `/api/v1/feedback/interaction` | Yes | Record an interaction event (view, click, dismiss). |

### POST /api/v1/feedback/rating

Request body:
```json
{ "item_id": "uuid", "rating": 4, "liked": true, "reasons": "great flavor", "comment": "optional" }
```

### POST /api/v1/feedback/interaction

Request body:
```json
{ "item_id": "uuid", "type": "view" }
```

Interaction types: `view`, `click`, `dismiss`, `purchase`.

---

## Menu Ingestion

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/ingestion/restaurants` | No | Create a restaurant (ingestion context). |
| GET | `/api/v1/ingestion/restaurants` | No | List all restaurants (ingestion context). |
| DELETE | `/api/v1/ingestion/restaurants/{restaurant_id}/menu` | No | Delete all menu items for a restaurant. |
| POST | `/api/v1/ingestion/upload/pdf` | No | Upload a PDF menu for extraction. |
| GET | `/api/v1/ingestion/uploads/{upload_id}` | No | Get upload processing status. |
| GET | `/api/v1/ingestion/uploads` | No | List all uploads. |

### POST /api/v1/ingestion/upload/pdf

Multipart form upload:
- `restaurant_id`: string (UUID)
- `file`: PDF file
- `currency`: string (optional)

Response:
```json
{
  "upload_id": "uuid",
  "restaurant_id": "uuid",
  "status": "COMPLETED",
  "items_created": 12,
  "items_failed": 0,
  "processing_time_seconds": 8.3,
  "notes": []
}
```

---

## Admin: Index Rebuilds

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/admin/rebuild/faiss-64d` | No | Trigger 64D FAISS index rebuild. |
| POST | `/api/v1/admin/rebuild/faiss-1536d` | No | Trigger 1536D FAISS index rebuild. |
| POST | `/api/v1/admin/rebuild/similarity-matrix` | No | Trigger similarity matrix rebuild. |
| POST | `/api/v1/admin/rebuild/all` | No | Trigger all index rebuilds. |
| GET | `/api/v1/admin/rebuild/status` | No | Get current rebuild status. |

Rebuild operations run in background threads. Check status via the GET endpoint.
