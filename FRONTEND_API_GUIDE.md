# TasteBud Backend API - Frontend Integration Guide

**Version:** 0.1.0 (MVP)  
**Base URL:** `http://localhost:8000/api/v1`  
**Updated:** January 27, 2026

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [API Endpoints](#api-endpoints)
   - [Health Check](#health-check)
   - [User Onboarding](#user-onboarding)
   - [User Preferences](#user-preferences)
   - [Restaurants](#restaurants)
   - [Menu Items](#menu-items)
   - [Recommendations](#recommendations)
   - [Similar Items](#similar-items)
   - [Search](#search)
   - [Feedback](#feedback)
4. [Data Models](#data-models)
5. [Error Handling](#error-handling)
6. [Example Flows](#example-flows)

---

## Overview

TasteBud Backend is a neural hybrid recommendation system powered by:
- **FAISS** for fast similarity search
- **GPT-4** for onboarding and explanations
- **Context-aware reranking** for personalized recommendations
- **Safety-first filtering** for allergies and dietary restrictions

The MVP provides three core features:
1. **Restaurant & Menu Discovery** - Browse restaurants and their menus
2. **Personalized Recommendations** - Get AI-powered dish suggestions
3. **Feedback Collection** - Help users improve recommendations over time

---

## Authentication

**Current Status:** No authentication required for MVP

All endpoints are publicly accessible. User identification is handled via `user_id` UUID parameter.

**Future:** Will implement JWT-based authentication with user sessions.

---

## API Endpoints

### Health Check

#### `GET /health`

Check if the API is running.

**Response:**
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

---

## User Onboarding

The onboarding flow uses a "Would You Rather" game to learn user taste preferences.

### Start Onboarding

#### `POST /onboarding/start`

Initialize onboarding for a new or existing user.

**Request Body:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "question_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "prompt": "Would you rather have:",
  "options": [
    {
      "id": "opt_a",
      "label": "Spicy Thai Curry with coconut milk",
      "tags": ["spicy", "savory", "creamy"],
      "ingredient_keys": ["coconut_milk", "curry_paste", "chili"]
    },
    {
      "id": "opt_b",
      "label": "Sweet Honey Glazed Salmon with caramelized onions",
      "tags": ["sweet", "savory", "umami"],
      "ingredient_keys": ["honey", "salmon", "caramelized_onions"]
    }
  ],
  "axis_hints": {
    "sweet": 0.3,
    "spicy": 0.7
  }
}
```

### Submit Answer

#### `POST /onboarding/answer`

Submit user's choice and get next question or completion status.

**Request Body:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "question_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "chosen_option_id": "opt_a"
}
```

**Response (More Questions):**
```json
{
  "complete": false,
  "question_id": "8d1f7780-8536-51ef-b825-f18gd2g01bf8",
  "prompt": "Would you rather have:",
  "options": [...],
  "axis_hints": {...}
}
```

**Response (Onboarding Complete):**
```json
{
  "complete": true,
  "message": "Onboarding complete! Your taste profile has been created.",
  "taste_vector": {
    "sweet": 0.45,
    "sour": 0.32,
    "salty": 0.68,
    "bitter": 0.25,
    "umami": 0.71,
    "spicy": 0.82,
    "fattiness": 0.54,
    "acidity": 0.38,
    "crunch": 0.61,
    "temp_hot": 0.73
  }
}
```

### Check Onboarding Status

#### `GET /onboarding/state`

Get current onboarding progress.

**Query Parameters:**
- `user_id` (required): UUID

**Response:**
```json
{
  "active": true,
  "confidence": 0.65,
  "answered_pairs": 4,
  "pending_axes": ["bitter", "acidity"]
}
```

---

## User Preferences

### Get User Profile

#### `GET /users/{user_id}/profile`

Get complete user profile including taste vector and preferences.

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "allergies": ["peanuts", "shellfish"],
  "dietary_rules": ["vegetarian", "gluten-free"],
  "liked_ingredients": ["avocado", "tomato", "basil"],
  "disliked_ingredients": ["cilantro", "olives"],
  "taste_vector": {
    "sweet": 0.45,
    "sour": 0.32,
    ...
  },
  "cuisine_affinity": {
    "italian": 0.82,
    "mexican": 0.71,
    "japanese": 0.54
  }
}
```

### Update User Preferences

#### `PATCH /users/{user_id}/preferences`

Update user allergies, dietary restrictions, and ingredient preferences.

**Request Body:**
```json
{
  "allergies": ["peanuts", "shellfish", "tree nuts"],
  "dietary_rules": ["vegan"],
  "liked_ingredients": ["mushrooms", "garlic"],
  "disliked_ingredients": ["cilantro"]
}
```

**Response:**
```json
{
  "status": "ok",
  "message": "Preferences updated successfully"
}
```

---

## Restaurants

### List All Restaurants

#### `GET /restaurants`

Get all available restaurants.

**Response:**
```json
[
  {
    "id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
    "name": "Spice Garden",
    "location": "123 Main St, San Francisco, CA",
    "tags": ["thai", "asian", "spicy", "casual"]
  },
  {
    "id": "b2c3d4e5-f6a7-5b6c-9d0e-1f2a3b4c5d6e",
    "name": "La Trattoria",
    "location": "456 Oak Ave, San Francisco, CA",
    "tags": ["italian", "pasta", "fine-dining"]
  }
]
```

### Get Restaurant Details

#### `GET /restaurants/{restaurant_id}`

Get detailed information about a specific restaurant including menu statistics.

**Response:**
```json
{
  "id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
  "name": "Spice Garden",
  "location": "123 Main St, San Francisco, CA",
  "tags": ["thai", "asian", "spicy", "casual"],
  "menu_count": 42,
  "cuisines": ["thai", "vietnamese", "asian-fusion"],
  "price_range": {
    "min": 8.99,
    "max": 24.99
  },
  "dietary_options": ["vegetarian", "vegan", "gluten-free"]
}
```

### Create Restaurant

#### `POST /restaurants`

Create a new restaurant (admin function).

**Request Body:**
```json
{
  "name": "New Restaurant",
  "location": "789 Pine St, San Francisco, CA",
  "tags": ["american", "burgers", "casual"]
}
```

**Response:**
```json
{
  "id": "c3d4e5f6-a7b8-6c7d-0e1f-2a3b4c5d6e7f",
  "name": "New Restaurant",
  "location": "789 Pine St, San Francisco, CA",
  "tags": ["american", "burgers", "casual"]
}
```

### Get Restaurant Menu

#### `GET /restaurants/{restaurant_id}/menu`

Get all menu items for a restaurant.

**Response:**
```json
[
  {
    "id": "d4e5f6a7-b8c9-7d8e-1f2a-3b4c5d6e7f8a",
    "name": "Pad Thai",
    "description": "Classic Thai stir-fried rice noodles with shrimp, eggs, and peanuts",
    "price": 14.99,
    "cuisine": ["thai"],
    "dietary_tags": ["gluten-free-option"],
    "allergens": ["shellfish", "peanuts", "eggs"],
    "spice_level": 2
  },
  ...
]
```

---

## Menu Items

### Get Item Details

#### `GET /items/{item_id}`

Get complete details for a specific menu item.

**Response:**
```json
{
  "id": "d4e5f6a7-b8c9-7d8e-1f2a-3b4c5d6e7f8a",
  "restaurant_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
  "restaurant_name": "Spice Garden",
  "name": "Pad Thai",
  "description": "Classic Thai stir-fried rice noodles with shrimp, eggs, and peanuts",
  "ingredients": ["rice_noodles", "shrimp", "eggs", "peanuts", "bean_sprouts", "lime"],
  "allergens": ["shellfish", "peanuts", "eggs"],
  "dietary_tags": ["gluten-free-option"],
  "cuisine": ["thai"],
  "price": 14.99,
  "spice_level": 2,
  "cooking_method": "stir-fried",
  "course": "main",
  "features": {
    "sweet": 0.6,
    "sour": 0.7,
    "salty": 0.8,
    "spicy": 0.5,
    "umami": 0.7
  },
  "provenance": {
    "source": "ingested",
    "method": "manual_entry"
  },
  "inference_confidence": 1.0
}
```

---

## Recommendations

### Get Personalized Recommendations

#### `GET /recommendations`

Get personalized dish recommendations based on user preferences and context.

**Query Parameters:**
- `user_id` (required): UUID - User identifier
- `restaurant_id` (optional): UUID - Filter by specific restaurant
- `top_n` (optional): integer - Number of recommendations (default: 10)
- `budget` (optional): float - Maximum price per item
- `time_of_day` (optional): string - "morning", "afternoon", "evening"
- `mood` (optional): string - "adventurous", "comfort", "healthy"
- `occasion` (optional): string - "date_night", "quick_bite", "celebration"

**Example Request:**
```
GET /recommendations?user_id=550e8400-e29b-41d4-a716-446655440000&top_n=5&budget=20&time_of_day=evening&mood=adventurous
```

**Response:**
```json
{
  "items": [
    {
      "item_id": "d4e5f6a7-b8c9-7d8e-1f2a-3b4c5d6e7f8a",
      "name": "Spicy Thai Basil Chicken",
      "score": 0.892,
      "matched_axes": ["spicy", "umami", "salty"],
      "reason": "Spicy Thai Basil Chicken matches your adventurous mood with its bold, spicy kick",
      "safety_flags": [],
      "cuisine": ["thai"],
      "price": 16.99,
      "confidence": 0.94,
      "provenance": {
        "source": "ingested",
        "inference_confidence": 1.0
      },
      "ranking_factors": {
        "taste_similarity": 0.82,
        "cuisine_affinity": 0.15,
        "popularity": 0.08,
        "ingredient_preferences": 0.05,
        "mood_adjustment": 0.10,
        "time_of_day_adjustment": 0.15
      }
    },
    ...
  ]
}
```

**Context Parameters Explained:**

- **`time_of_day`**: Boosts breakfast items in morning, dinner items in evening
- **`mood`**: 
  - `adventurous` - Boosts spicy, exotic cuisines
  - `comfort` - Boosts familiar, hearty dishes
  - `healthy` - Boosts low-calorie, vegetarian options
- **`occasion`**:
  - `date_night` - Boosts upscale, romantic restaurants
  - `quick_bite` - Boosts appetizers, sandwiches
  - `celebration` - Boosts premium, special dishes

---

## Similar Items

### Find Similar Dishes

#### `GET /items/{item_id}/similar`

Find dishes similar to a given item using FAISS similarity search.

**Query Parameters:**
- `k` (optional): integer - Number of similar items (default: 10)
- `cuisine` (optional): string - Filter by cuisine
- `max_price` (optional): float - Maximum price
- `dietary` (optional): string - Filter by dietary tag
- `explain` (optional): boolean - Include GPT explanations (default: false)

**Example Request:**
```
GET /items/d4e5f6a7-b8c9-7d8e-1f2a-3b4c5d6e7f8a/similar?k=5&explain=true
```

**Response:**
```json
{
  "item_id": "d4e5f6a7-b8c9-7d8e-1f2a-3b4c5d6e7f8a",
  "item_name": "Pad Thai",
  "similar_items": [
    {
      "id": "e5f6a7b8-c9d0-8e9f-2a3b-4c5d6e7f8a9b",
      "name": "Drunken Noodles",
      "description": "Spicy Thai stir-fried wide noodles",
      "price": 15.99,
      "cuisine": ["thai"],
      "dietary_tags": ["spicy"],
      "similarity_score": 0.9124,
      "explanation": "Both dishes share similar Thai flavors with stir-fried noodles and bold spices"
    },
    ...
  ],
  "metadata": {
    "total_candidates": 48,
    "filtered_count": 5,
    "filters_applied": {
      "cuisine": null,
      "max_price": null,
      "dietary": null
    }
  }
}
```

---

## Search

### Search Menu Items

#### `GET /search`

Search for menu items across all restaurants with filtering options.

**Query Parameters:**
- `q` (optional): string - Text search in name and description
- `cuisine` (optional): string - Filter by cuisine
- `dietary` (optional): string - Filter by dietary tag
- `max_price` (optional): float - Maximum price
- `min_price` (optional): float - Minimum price
- `restaurant_id` (optional): UUID - Filter by restaurant
- `limit` (optional): integer - Maximum results (default: 50)

**Example Request:**
```
GET /search?q=noodles&cuisine=thai&max_price=20&limit=10
```

**Response:**
```json
{
  "items": [
    {
      "id": "d4e5f6a7-b8c9-7d8e-1f2a-3b4c5d6e7f8a",
      "name": "Pad Thai",
      "description": "Classic Thai stir-fried rice noodles",
      "restaurant_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
      "restaurant_name": "Spice Garden",
      "cuisine": ["thai"],
      "dietary_tags": ["gluten-free-option"],
      "price": 14.99,
      "allergens": ["shellfish", "peanuts", "eggs"]
    },
    ...
  ],
  "count": 7,
  "filters_applied": {
    "query": "noodles",
    "cuisine": "thai",
    "dietary": null,
    "max_price": 20.0,
    "min_price": null,
    "restaurant_id": null
  }
}
```

---

## Feedback

### Submit Rating

#### `POST /feedback/rating`

Submit a rating for a menu item to improve future recommendations.

**Request Body:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "item_id": "d4e5f6a7-b8c9-7d8e-1f2a-3b4c5d6e7f8a",
  "rating": 5,
  "liked": true,
  "reasons": ["delicious", "perfect_spice_level", "great_value"],
  "comment": "Best Pad Thai I've ever had!"
}
```

**Fields:**
- `rating`: integer (1-5 scale)
- `liked`: boolean - Quick like/dislike
- `reasons`: array of strings - Why they liked/disliked
  - Positive: `"delicious"`, `"perfect_spice_level"`, `"great_value"`, `"authentic"`, `"creative"`
  - Negative: `"too_spicy"`, `"too_bland"`, `"overpriced"`, `"poor_quality"`
- `comment`: optional string - Free-form feedback

**Response:**
```json
{
  "status": "ok",
  "message": "Feedback recorded and taste profile updated"
}
```

### Quick Like/Dislike

#### `POST /discovery/quick-like`

Quick feedback for rapid learning (lighter weight than full rating).

**Request Body:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "item_id": "d4e5f6a7-b8c9-7d8e-1f2a-3b4c5d6e7f8a",
  "liked": true
}
```

**Response:**
```json
{
  "status": "ok"
}
```

### Track Interaction

#### `POST /feedback/interaction`

Track user interactions for engagement metrics.

**Request Body:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "item_id": "d4e5f6a7-b8c9-7d8e-1f2a-3b4c5d6e7f8a",
  "interaction_type": "view",
  "context": {
    "screen": "recommendations",
    "position": 1
  }
}
```

**Interaction Types:**
- `view` - User viewed the item
- `click` - User clicked for details
- `dismiss` - User dismissed the recommendation
- `purchase` - User ordered the item

**Response:**
```json
{
  "status": "ok"
}
```

---

## Data Models

### User

```typescript
interface User {
  id: string;  // UUID
  allergies: string[];
  dietary_rules: string[];
  liked_ingredients: string[];
  disliked_ingredients: string[];
  taste_vector: {
    sweet: number;      // 0.0 - 1.0
    sour: number;
    salty: number;
    bitter: number;
    umami: number;
    spicy: number;
    fattiness: number;
    acidity: number;
    crunch: number;
    temp_hot: number;
  };
  cuisine_affinity: {
    [cuisine: string]: number;  // 0.0 - 1.0
  };
}
```

### MenuItem

```typescript
interface MenuItem {
  id: string;  // UUID
  restaurant_id: string;  // UUID
  name: string;
  description: string | null;
  ingredients: string[];
  allergens: string[];
  dietary_tags: string[];
  cuisine: string[];
  price: number | null;
  spice_level: number | null;  // 0-5
  cooking_method: string | null;
  course: string | null;
  features: {
    [axis: string]: number;  // Taste features 0.0 - 1.0
  };
  provenance: {
    source: "ingested" | "gpt_inferred";
    method?: string;
  };
  inference_confidence: number;  // 0.0 - 1.0
}
```

### Restaurant

```typescript
interface Restaurant {
  id: string;  // UUID
  name: string;
  location: string | null;
  tags: string[];
}
```

---

## Error Handling

All errors follow a consistent format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

### HTTP Status Codes

- `200 OK` - Success
- `400 Bad Request` - Invalid input or parameters
- `404 Not Found` - Resource doesn't exist
- `422 Unprocessable Entity` - Validation error
- `500 Internal Server Error` - Server error
- `503 Service Unavailable` - Service temporarily unavailable (e.g., FAISS index not built)

### Common Error Scenarios

**User Not Found:**
```json
{
  "detail": "user not found"
}
```

**Item Not Found:**
```json
{
  "detail": "item not found"
}
```

**FAISS Index Not Available:**
```json
{
  "detail": "FAISS index not built. Please run the index builder script."
}
```

**No Safe Items:**
```json
{
  "items": [],
  "warnings": ["no_safe_items"]
}
```

---

## Example Flows

### Flow 1: New User Onboarding

```typescript
// 1. Start onboarding
POST /onboarding/start
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000"
}

// 2. Answer questions (repeat until complete)
POST /onboarding/answer
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "question_id": "...",
  "chosen_option_id": "opt_a"
}

// 3. Set dietary preferences
PATCH /users/550e8400-e29b-41d4-a716-446655440000/preferences
{
  "allergies": ["peanuts"],
  "dietary_rules": ["vegetarian"]
}
```

### Flow 2: Get Recommendations

```typescript
// 1. Browse restaurants
GET /restaurants

// 2. Get restaurant details
GET /restaurants/a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d

// 3. Get personalized recommendations
GET /recommendations?user_id=550e8400-e29b-41d4-a716-446655440000
    &restaurant_id=a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d
    &top_n=10&budget=25&time_of_day=evening&mood=adventurous

// 4. View item details
GET /items/d4e5f6a7-b8c9-7d8e-1f2a-3b4c5d6e7f8a

// 5. Find similar items
GET /items/d4e5f6a7-b8c9-7d8e-1f2a-3b4c5d6e7f8a/similar?k=5
```

### Flow 3: Submit Feedback

```typescript
// 1. User views item
POST /feedback/interaction
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "item_id": "d4e5f6a7-b8c9-7d8e-1f2a-3b4c5d6e7f8a",
  "interaction_type": "view"
}

// 2. User rates item
POST /feedback/rating
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "item_id": "d4e5f6a7-b8c9-7d8e-1f2a-3b4c5d6e7f8a",
  "rating": 5,
  "liked": true,
  "reasons": ["delicious", "perfect_spice_level"],
  "comment": "Amazing!"
}

// 3. Quick like for rapid learning
POST /discovery/quick-like
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "item_id": "e5f6a7b8-c9d0-8e9f-2a3b-4c5d6e7f8a9b",
  "liked": true
}
```

### Flow 4: Search and Filter

```typescript
// 1. Search for specific items
GET /search?q=pasta&cuisine=italian&max_price=20&limit=10

// 2. Filter by dietary needs
GET /search?dietary=vegan&max_price=15

// 3. Browse restaurant menu with filters
GET /restaurants/a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d/menu
```

---

## Performance Notes

- **Recommendations**: <500ms with FAISS, <2s with SQL fallback
- **Similar Items**: <100ms for 10K item catalog
- **Search**: <200ms for basic text search
- **FAISS Index**: Loaded once at startup, cached in memory

---

## Rate Limits

**Current MVP:** No rate limits enforced

**Recommended for Production:**
- 100 requests/minute per user for recommendations
- 1000 requests/minute per user for search/browse
- 10 requests/minute for feedback submission

---

## Support

For issues or questions:
- Check logs in `logs/` directory
- Review [README.md](README.md) for setup instructions
- See [ISSUES/](ISSUES/) directory for known issues and roadmap

---

## Changelog

### v0.1.0 (January 27, 2026) - MVP Release

**Added:**
- New FAISS-powered retrieval service
- Context-aware reranking with time/mood/occasion
- Template-based explanations with GPT fallback
- Frontend-critical endpoints (item details, restaurant details, search)
- Comprehensive API documentation

**Enhanced:**
- Recommendation endpoint now supports `mood` and `occasion` parameters
- Ranking factors exposed in recommendation response
- Better error messages and logging

**Breaking Changes:**
- Recommendation service now uses new pipeline by default
- Response format includes additional `ranking_factors` field

---

*Last Updated: January 27, 2026*
