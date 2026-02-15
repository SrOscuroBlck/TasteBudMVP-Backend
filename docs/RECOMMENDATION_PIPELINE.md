# TasteBud Backend -- Recommendation Pipeline

This document explains how the recommendation system works, from user profile construction through candidate retrieval, scoring, diversity reranking, and meal composition.

---

## Pipeline Stages

```
1. User Profile Construction (onboarding + ongoing feedback)
        |
        v
2. Candidate Retrieval (FAISS ANN search + safety filters)
        |
        v
3. Scoring and Reranking (taste similarity + cuisine + popularity + Bayesian exploration)
        |
        v
4. ML Reranking (optional trained model)
        |
        v
5. Diversity Reranking (MMR with cuisine/price constraints)
        |
        v
6. Meal Composition (multi-course assembly, if full meal intent)
        |
        v
7. Explanation Generation (LLM-generated rationale per item)
        |
        v
8. In-Session Learning (real-time adjustments from feedback)
```

---

## 1. User Profile Construction

### Onboarding

New users go through a "Would You Rather?" onboarding flow that asks up to 7 pairwise comparison questions. Each question targets the taste axis with the highest current uncertainty.

The process:
- Start with population priors (global mean and variance per taste axis)
- GPT generates contextual pairwise questions (Option A vs. Option B)
- Each answer updates the user's taste vector and reduces uncertainty on the targeted axis
- Early stop when all axis uncertainties drop below the confidence threshold (0.8)
- Assign a taste archetype (nearest cluster center) on completion

### Bayesian Taste Profile

Each user has a `BayesianTasteProfile` that models preferences as Beta distributions:

- One Beta(alpha, beta) distribution per taste axis (7 total) plus per-cuisine distributions
- **Posterior updates**: when a user likes an item with high sweetness, the sweet axis alpha increases; dislikes decrease alpha and increase beta
- **Thompson Sampling**: during recommendation, sample from the posterior rather than using the mean -- this naturally balances exploration (trying new taste axes) with exploitation (favoring known preferences)
- **Uncertainty decay**: as more feedback accumulates, the distributions narrow, reducing exploration

### Ongoing Learning

After onboarding, the profile continues evolving through:
- **Ratings** (1-5 scale): strong signal, large Bayesian update
- **Likes/dislikes**: moderate signal
- **Quick likes** (discovery): small nudge
- **Post-meal feedback**: satisfaction and taste match ratings
- **Temporal decay**: older feedback has less influence (half-life: 21 days)
- **Ingredient penalties**: cross-restaurant learning of ingredient-level preferences

---

## 2. Candidate Retrieval

**Service**: `RetrievalService` (services/core/retrieval_service.py)

The retrieval stage finds a broad set of candidate items before scoring.

### FAISS Approximate Nearest Neighbor Search

- The user's taste vector (or a contextually adjusted version) is used as the query vector
- FAISS searches the 64D or 1536D index for the nearest neighbors
- Returns a candidate pool (typically 3x the requested result count)
- Falls back to SQL-based retrieval if no FAISS index is loaded

### Safety Filters (Hard Constraints)

After retrieval, candidates are filtered to remove:
- Items containing any of the user's declared allergens
- Items violating the user's dietary rules (e.g., meat items for vegetarians)
- Items on the user's permanently excluded list
- Items already shown in the current session

These filters are deterministic and independent of GPT. They never let through an unsafe item regardless of how high it scores.

---

## 3. Scoring and Reranking

**Service**: `RerankingService` (services/core/reranking_service.py)

Each candidate receives a composite score from multiple signals:

### Taste Similarity

Cosine similarity between the user's taste vector and the item's feature vector (7D). This is the primary scoring signal.

### Cuisine Affinity

If the user has learned cuisine preferences (e.g., Italian: 0.8, Japanese: 0.6), items matching preferred cuisines get a boost. Controlled by `lambda_cuisine` (default: 0.2).

### Popularity

Global and per-restaurant item popularity, with temporal decay. Controlled by `lambda_pop` (default: 0.2).

### Bayesian Exploration

Thompson Sampling from the Bayesian profile adds stochastic exploration. Rather than always recommending the highest-mean items, the system samples from the posterior and occasionally surfaces items that are uncertain but potentially good. Controlled by `exploration_coefficient` (default: 0.2).

### Time-of-Day Context

Contextual adjustments based on the time of day (e.g., lighter items for breakfast, heartier for dinner).

### Ingredient Penalties

Learned negative weights for specific ingredients the user has historically disliked across restaurants.

### GPT Confidence Discount

Items whose features were inferred by GPT (rather than explicitly provided) receive a scoring penalty proportional to their inference uncertainty. Controlled by `gpt_confidence_discount` (default: 0.3).

### Per-User Learned Weights

Each user has a `UserScoringWeights` record with individually learned weights for the taste, cuisine, popularity, and exploration components. These weights are updated via online learning after each feedback signal.

---

## 4. ML Reranking (Optional)

**Service**: `MLRerankingService` (services/ml/ml_reranking_service.py)

An optional learned reranking model that can override or blend with the scoring formula. This is a pluggable stage for training task-specific models.

---

## 5. Diversity Reranking (MMR)

**Service**: `MMRService` (services/diversity/mmr_service.py)

After scoring, Maximal Marginal Relevance (MMR) reranks results to balance relevance with diversity:

$$\text{MMR}(d_i) = \alpha \cdot \text{Score}(d_i) - (1 - \alpha) \cdot \max_{d_j \in S} \text{Sim}(d_i, d_j)$$

Where:
- $\alpha$ is the relevance/diversity tradeoff (default: 0.7, favoring relevance)
- $\text{Score}(d_i)$ is the composite score from Stage 3
- $S$ is the set of already-selected items
- $\text{Sim}$ uses the pre-computed similarity matrix

### Diversity Constraints

MMR also enforces hard constraints:
- Maximum items per cuisine (configurable, prevents cuisine domination)
- Price range distribution (avoids clustering at one price point)
- Course diversity (spreads across appetizers, mains, desserts when appropriate)

---

## 6. Meal Composition

**Service**: `MealCompositionService` (services/composition/meal_composition_service.py)

When `meal_intent` is `FULL_MEAL`, the system assembles a multi-course meal suggestion:

### Composition Steps

1. Group scored items by course (appetizer, main, dessert)
2. Select the top candidate for each course
3. Score the combination for flavor harmony using `HarmonyService`
4. Generate alternative compositions if the primary one scores poorly
5. Return the best composition for user validation

### Flavor Harmony

The `HarmonyService` evaluates how well courses complement each other:
- Taste contrast (e.g., a rich main benefits from a lighter appetizer)
- Texture variety (mixing crunchy, creamy, chewy)
- Cuisine coherence (items from compatible cuisines score higher)
- Price balance (total within budget constraint)

Users can provide per-course feedback on compositions (accept/reject individual courses), triggering recomposition with constraints.

---

## 7. Explanation Generation

**Service**: `ExplanationService` (services/explanation/explanation_service.py)

Each recommended item gets a human-readable explanation of why it was recommended:

- **LLM-first approach** (default): GPT generates personalized explanations referencing the user's taste profile, the item's attributes, and why they match
- **Fallback**: template-based explanations built from the scoring components (e.g., "Matches your preference for umami flavors")
- **Enhancement**: `ExplanationEnhancementService` adds contextual details (time appropriateness, past orders)
- **Personalization**: `PersonalizedExplanationService` tailors language to the user's experience level

---

## 8. In-Session Learning

**Service**: `InSessionLearningService` (services/learning/in_session_learning_service.py)

Within a single session, user feedback causes real-time preference adjustments:

- **Like**: boost similar taste axes for remaining recommendations in the session
- **Dislike**: suppress similar items, adjust taste vector temporarily
- **Skip**: mild negative signal
- **Selected**: strong positive signal, similar to like

These adjustments are ephemeral (session-scoped). Permanent profile updates happen via `UnifiedFeedbackService` after the session.

---

## Session Lifecycle

A typical recommendation session follows this flow:

```
1. POST /sessions/start
   - Create session with restaurant, meal intent, budget, constraints
   - Capture context snapshot (time, day, user experience level)
   - Check visit history (repeat visitor detection)

2. POST /sessions/{id}/next  (repeated)
   - Run full pipeline: retrieval -> reranking -> MMR -> composition -> explanation
   - Track shown items to avoid repeats
   - Apply in-session learning from previous feedback
   - Return next batch of recommendations

3. POST /sessions/{id}/feedback  (interleaved with step 2)
   - Record like/dislike/skip/save/select on individual items
   - Trigger in-session learning adjustments
   - Update excluded items list

4. POST /sessions/{id}/complete
   - Record selected items
   - Create order history entries
   - Trigger permanent profile updates via UnifiedFeedbackService
   - Schedule post-meal feedback email

5. POST /feedback/post-meal  (later)
   - Submit satisfaction, taste match, and other ratings
   - Final Bayesian profile update with post-meal signals
```

---

## Key Algorithms

### Cosine Similarity (Taste Matching)

The primary scoring function computes cosine similarity between the user's 7D taste vector and each item's feature vector:

$$\text{sim}(u, i) = \frac{\vec{u} \cdot \vec{i}}{\|\vec{u}\| \cdot \|\vec{i}\|}$$

Implemented in `services/features/features.py`.

### Thompson Sampling (Exploration)

For each recommendation request, the system samples from Beta posteriors rather than using point estimates:

$$\tilde{\theta}_k \sim \text{Beta}(\alpha_k, \beta_k) \quad \text{for each axis } k$$

This sampled vector replaces or blends with the mean taste vector during scoring. Items that are uncertain (wide posteriors) get occasional high samples, creating exploration.

### Temporal Decay

Older feedback contributes less to the profile:

$$w(t) = 2^{-t / h}$$

Where $t$ is the age of the feedback in days and $h$ is the half-life (default: 21 days).

### Composite Score

The final score for an item combines all signals with learned weights:

$$\text{Score}(i) = w_t \cdot \text{taste\_sim}(u, i) + w_c \cdot \text{cuisine}(u, i) + w_p \cdot \text{popularity}(i) + w_e \cdot \text{exploration}(i) - \text{penalties}(i)$$

Weights ($w_t, w_c, w_p, w_e$) are learned per-user via online gradient updates in `WeightLearningService`.
