# TasteBud: a phased plan from content-based to production-grade recommender

**TasteBud can evolve from a manually-annotated, single-user prototype to a production-caliber recommendation system through five focused phases — and most of the highest-impact improvements cost under $1/month in API calls.** 

The biggest immediate wins are replacing hand-coded taste vectors with LLM-generated ones (gpt-5-mini at $0.04 per 200 items), adding an exploration bonus using the existing uncertainty vector, and fixing cold start with population-based priors instead of flat 0.5 values. Longer-term, integrating Rappi as a primary menu data source for Cali, implementing Bayesian taste profiles with Thompson Sampling, and building a two-stage retrieval pipeline will transform recommendation quality. The plan below is organized into five phases, each with concrete implementations, dependency chains, effort estimates, and API cost projections — all executable by a coding agent against the existing Python/FastAPI codebase.

---

## Phase 1: Foundation fixes that deliver immediate quality gains

These changes address the most damaging known issues — unreliable taste vectors, broken cold start, and wasted FAISS capacity — with minimal architectural disruption. **Expected total effort: 2–3 weeks. Monthly API cost: ~$0.50.**

### 1.1 LLM-generated taste vectors (replaces manual annotation)

**What**: Use gpt-5-mini with structured JSON output to auto-generate 10-dimensional taste vectors from menu item descriptions, replacing the current unreliable manual process.

**Why it matters**: This is the single highest-leverage fix. Every downstream computation — scoring, harmony, learning — depends on taste vector accuracy. Manual annotation doesn't scale and introduces systematic bias.

**How to implement**: Call the OpenAI API with `response_format={"type": "json_object"}`, a culinary-expert system prompt, 3–5 few-shot examples of known dishes, and `temperature=0` for consistency. Validate outputs programmatically (all values in [0,1], required keys present). Batch-process existing items; run on new items at ingestion time.

```python
# Core call pattern — gpt-5-mini structured output
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-5-mini",
    response_format={"type": "json_object"},
    messages=[
        {"role": "system", "content": CULINARY_EXPERT_PROMPT},
        {"role": "user", "content": f"Rate '{dish_name}': {description}"}
    ],
    temperature=0
)
```

**Cost**: **$0.04 per 200 items** with gpt-5-mini ($0.15/1M input, $0.60/1M output). With Claude Haiku 4.5 Batch API at 50% discount: $0.15 per 200 items. At $15/month budget, you could process **75,000+ items/month** with gpt-5-mini.

**Effort**: 3–5 days. Includes prompt engineering, validation logic, batch processing script, and re-indexing existing items.

**Dependencies**: None. Drop-in replacement for current manual annotation.

### 1.2 Refined taste vector dimensions

**What**: Merge the redundant "sour" and "acidic" dimensions (sour IS the perception of acids), and separate texture ("crunchy") and temperature ("hot") into distinct vectors for cleaner modeling.

**Why it matters**: The current 10D vector conflates three sensory modalities — taste, texture, and temperature — into one space, which distorts cosine similarity calculations and confuses the learning signal.

**Recommended schema**:
- **Taste vector (7D)**: `[sweet, sour, salty, bitter, umami, fatty, spicy]` — covers the five basic tastes plus the two most culinarily relevant chemesthetic dimensions
- **Texture vector (3D)**: `[crunchy, creamy, chewy]` — optional, used for harmony scoring
- **Richness scalar (1D)**: `[richness]` — overall heaviness/lightness, critical for meal composition

The five basic tastes (sweet, sour, salty, bitter, umami) are scientifically established. Fat taste ("oleogustus") is gaining acceptance as a sixth. Spicy is technically a pain signal (TRPV1 receptors), not a taste — but it's indispensable for food recommendation, especially in Colombian cuisine.

**Effort**: 2–3 days. Update Pydantic models, re-generate vectors via the LLM pipeline from 1.1, update scoring logic.

**Dependencies**: 1.1 (LLM pipeline makes re-generation trivial).

### 1.3 Population-based priors for cold start

**What**: Replace flat 0.5 priors with data-informed initial taste vectors derived from dish clustering.

**Why it matters**: Flat priors produce effectively random initial recommendations. Even crude population priors dramatically improve first-session quality.

**Implementation**: Cluster existing menu items' taste vectors into **5–8 archetypes** (e.g., "Comfort Food Lover," "Spice Adventurer," "Health Conscious") using K-Means. During onboarding, a 3-question flow identifies the closest archetype. The cluster centroid becomes the initial taste vector.

```python
from sklearn.cluster import KMeans
archetypes = KMeans(n_clusters=6).fit(all_taste_vectors)
# At onboarding: identify closest archetype → use centroid as initial profile
```

**Effort**: 3–4 days. Includes clustering analysis, archetype labeling, and onboarding endpoint.

**Dependencies**: 1.1 (needs quality taste vectors to cluster).

### 1.4 Activate FAISS for embedding retrieval

**What**: Use the existing 768-dim text-embedding-3-small vectors in FAISS `IndexFlatIP` as a first-stage retrieval system, plus pre-compute a pairwise similarity matrix for harmony scoring.

**Why it matters**: Currently, FAISS is integrated but underutilized — the system scores all 200+ items linearly. With FAISS, retrieval becomes sub-millisecond, and pre-computed harmony matrices eliminate redundant computation in multi-course composition.

**Implementation**:
- Load normalized embeddings into `faiss.IndexFlatIP` at startup
- For **200–5,000 items**, brute-force exact search is optimal (no need for IVF/HNSW)
- Pre-compute the full N×N pairwise cosine similarity matrix at startup (**25M floats ≈ 100MB for 5,000 items**) for instant harmony lookups
- Cache embedding API responses with long TTL (menu items change infrequently)

**Quick upgrade**: Switch from `text-embedding-3-small` to **`text-embedding-3-large` with `dimensions=768`** — drop-in compatible with existing index, better embeddings, cost increase from $0.02→$0.13/1M tokens (negligible at this scale: **$0.065 to embed 5,000 items**).

**Effort**: 2–3 days. Mostly wiring up the startup precomputation and modifying the scoring pipeline to use FAISS results.

**Dependencies**: None.

### 1.5 Temporal feedback decay

**What**: Weight recent feedback more heavily using exponential decay with a configurable half-life.

**Why it matters**: A dislike from 6 months ago shouldn't carry the same weight as a like from yesterday. Food preferences drift seasonally and with life changes.

**Formula**: `w(t) = 0.5^(Δt / T_half)` where **T_half ≈ 21 days** is a good starting point for food preferences.

```python
def temporal_weight(feedback_time, half_life_days=21):
    delta_days = (datetime.now() - feedback_time).total_seconds() / 86400
    return 0.5 ** (delta_days / half_life_days)
```

Apply this weight to all taste vector update calculations and cuisine affinity adjustments.

**Effort**: 1–2 days. Modify the feedback update functions to multiply by `temporal_weight`.

**Dependencies**: None.

---

## Phase 2: The intelligence layer — exploration, Bayesian profiles, and better scoring

These improvements transform TasteBud from a static scorer into an adaptive system that learns efficiently and balances known preferences with discovery. **Expected total effort: 3–4 weeks. Monthly API cost: ~$0 (all local computation).**

### 2.1 Exploration bonus using the existing uncertainty vector

**What**: Add an exploration term to the scoring formula that rewards items in taste dimensions where the system is most uncertain about user preferences.

**Why it matters**: This is the cheapest fix for the diversity problem and filter bubble risk. The uncertainty vector already exists — it just isn't used for scoring.

**Modified scoring formula**:
```
score = α·cos(v', f) + β·C(i,u) + γ·popularity + δ·novelty + ε·repeat_penalty
        + c · dot(uncertainty_vec, |item.feature_vec|)
```

The parameter **c** controls exploration strength (start at 0.2, tune over time). Items that are strong on taste dimensions where user preferences are uncertain get boosted.

**Effort**: 1 day. Single-line addition to scoring function plus a config parameter.

**Dependencies**: None.

### 2.2 Bayesian taste profiles with Thompson Sampling

**What**: Model each taste dimension as a `Beta(α, β)` distribution instead of a point estimate. Use Thompson Sampling for recommendation: sample from each dimension's posterior, compute similarity with the sampled vector.

**Why it matters**: This replaces three separate mechanisms (taste vector, uncertainty vector, exploration heuristic) with a single principled framework. Thompson Sampling naturally explores uncertain dimensions and exploits known preferences — **no tuning of exploration parameters needed**.

```python
class BayesianTasteProfile:
    def __init__(self, n_dims=7):
        self.alpha = np.full(n_dims, 2.0)  # Beta(2,2) prior: mild center preference
        self.beta = np.full(n_dims, 2.0)

    def sample_taste(self):
        return np.array([np.random.beta(self.alpha[d], self.beta[d]) for d in range(len(self.alpha))])

    def update(self, item_features, liked, weight=1.0):
        for d in range(len(self.alpha)):
            relevance = item_features[d] * weight
            if liked: self.alpha[d] += relevance
            else: self.beta[d] += relevance
```

Integrate with temporal decay: multiply `weight` by the decay factor from 1.5. The uncertainty property (`α·β / ((α+β)² · (α+β+1))`) naturally replaces the hand-maintained uncertainty vector.

**Effort**: 1 week. Replace taste vector update logic, modify scoring to use sampled vectors, migrate existing feedback history into Beta parameters.

**Dependencies**: 1.2 (refined dimensions), 1.5 (temporal decay).

### 2.3 Fix cuisine over-penalization

**What**: Replace the current binary cuisine affinity update with a Bayesian approach that distinguishes between "this specific dish was bad" and "I don't like this cuisine."

**Implementation**: Track cuisine affinity as `Beta(α_cuisine, β_cuisine)` like taste dimensions. One bad Italian dish adds ~0.3 to β_Italian (a mild negative). The mean `α/(α+β)` shifts slightly but doesn't tank to zero. After 5+ positive Italian experiences, one negative barely moves the needle.

**Additional fix**: Weight cuisine updates by the **magnitude of dish-cuisine typicality**. A fusion dish that's only marginally Italian should barely affect Italian affinity. Use the LLM to assign cuisine-typicality scores (0–1) during item ingestion.

**Effort**: 2–3 days.

**Dependencies**: 2.2 (Bayesian framework).

### 2.4 Two-stage retrieval pipeline

**What**: Stage 1 uses FAISS to retrieve top-30 candidates by embedding similarity. Stage 2 applies the full feature-based scoring formula (taste match, cuisine affinity, diversity, exploration) to re-rank.

**Why it matters**: Decouples "what's semantically relevant" from "what matches this user's preferences." Enables future scaling to thousands of items without scoring every one.

For queries like "something like pad thai but spicier," concatenate the base description with the modifier and embed the combined string — the embedding space naturally captures this.

**Optional enhancement**: Add a **cross-encoder re-ranker** (`cross-encoder/ms-marco-MiniLM-L-6-v2`, 22M params) for query-based searches. At 30 candidates, inference takes ~150ms — acceptable for real-time use.

```python
# Stage 1: FAISS retrieval
candidates = retriever.retrieve(query_embedding, k=30)
# Stage 2: Feature-based reranking
final = reranker.score(candidates, user_profile, session_context)
return final[:10]
```

**Effort**: 1 week. Refactor scoring pipeline into retrieve → rerank stages.

**Dependencies**: 1.4 (FAISS activation).

### 2.5 Improved harmony scoring for multi-course composition

**What**: Replace the current composition scoring with a multi-dimensional harmony metric based on flavor science.

**Three harmony dimensions to implement**:

1. **Taste contrast scoring**: Reward complementary pairings (acidic appetizer → rich main → sweet dessert). Penalize repeating the dominant taste dimension across courses. Based on established culinary rules: fatty+acidic = bonus, sweet+salty = bonus, umami+umami = synergistic bonus.

2. **Intensity arc**: Score whether the meal follows a natural intensity progression (lighter → heavier → sweet resolution). Compute richness scores per course and reward monotonic appetizer→main progression.

3. **Ingredient diversity**: Penalize repeated primary ingredients across courses (no chicken appetizer + chicken main). Use the LLM-extracted ingredient lists from Phase 1.

```python
def harmony_score(appetizer, main, dessert):
    contrast = taste_contrast_score(appetizer.taste_vec, main.taste_vec, dessert.taste_vec)
    arc = intensity_arc_score(appetizer.richness, main.richness, dessert.sweetness)
    diversity = ingredient_diversity_penalty(appetizer.ingredients, main.ingredients)
    return 0.4 * contrast + 0.3 * arc + 0.3 * diversity
```

The Ahn et al. flavor network research shows Western cuisines pair ingredients sharing many flavor compounds (complementary pairing), while East Asian cuisines tend to avoid shared compounds (contrasting pairing). **For Colombian cuisine, which blends both traditions**, the harmony score should reward moderate compound overlap — neither maximizing nor minimizing it.

**Effort**: 1 week.

**Dependencies**: 1.1 (LLM ingredient extraction), 1.2 (refined taste vectors).

### 2.6 Dynamic weight learning

**What**: Learn the scoring weights α, β, γ, δ, ε from user feedback instead of hardcoding them.

**Two-track approach**:
- **Real-time**: Online gradient descent updates weights after each feedback event. Learning rate 0.01, weights projected to simplex (non-negative, sum to 1).
- **Periodic calibration**: Every 50 interactions, run Bayesian optimization via **Optuna** over accumulated history to find globally optimal weights.

```python
import optuna
def objective(trial):
    weights = [trial.suggest_float(f'w{i}', 0.01, 1.0) for i in range(5)]
    weights = np.array(weights) / sum(weights)
    return evaluate_weights(weights, feedback_history)
study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=100)
```

**Effort**: 3–4 days.

**Dependencies**: Sufficient feedback history (~30+ interactions).

---

## Phase 3: The data pipeline — sourcing real menus for Cali, Colombia

This phase builds the ingestion infrastructure to populate TasteBud with real restaurant data. **Expected total effort: 2–3 weeks. Monthly cost: $5–15.**

### 3.1 Restaurant discovery via Google Places API

**What**: Use the Places API (New) to discover restaurants in Cali with coordinates, ratings, price levels, categories, photos, and hours. Google provides **$200/month free credit**, covering ~5,700 requests.

```python
import googlemaps
gmaps = googlemaps.Client(key='YOUR_KEY')
results = gmaps.places_nearby(
    location=(3.4516, -76.5320),  # Cali, Colombia
    radius=5000, type='restaurant'
)
```

**Limitation**: Google Places returns restaurant metadata but **not individual menu items**. Menu data requires a separate source.

**Python package**: `googlemaps`. **Cost**: Free within $200 credit.

**Effort**: 2–3 days.

### 3.2 Menu data from Rappi (primary source for Cali)

**What**: Rappi is Colombia's dominant food delivery platform (founded in Bogotá, 2015) with strong Cali coverage. It's the single best source for structured menu data in the region.

**Three access strategies**:
1. **Official API** (`dev-portal.rappi.com`): Requires partner registration. Endpoints include `GET /api/v2/restaurants-integrations-public-api/menu/{storeId}` for full menu data with prices, categories, and modifiers. Uses OAuth bearer tokens.
2. **Apify Rappi Scraper** (`apify.com/parseforge/rappi-scraper`): No-code scraper extracting restaurant listings, ratings, full menus. Free tier: 100 items. Paid: scales to 1M+ items. Python client: `apify-client`.
3. **Direct store lookup**: `https://api-lbs.rappi.com/api/v2/stores?latitude=3.4516&longitude=-76.5320` returns nearby restaurants with store IDs for menu retrieval.

**Supplementary source**: **PedidosYa** (Delivery Hero subsidiary, present in Cali) via **DoubleData** API for real-time menu data, delivery fees, and restaurant availability. Enterprise pricing — contact for quotes.

**Data structure from Rappi**: Restaurant → Categories → Items (name, description, price in COP, SKU, modifiers/toppings). Prices typically range **5,000–50,000 COP**.

**Cost**: Apify starter ~$5–10/month for periodic menu scraping. **Effort**: 1 week.

### 3.3 LLM-powered menu processing pipeline

**What**: A three-stage pipeline that transforms raw menu data into the full item representation TasteBud needs.

**Stage A — Ingredient and allergen extraction**: Prompt gpt-5-mini to extract ingredients, likely allergens, and dietary tags from each item description. For items with photos, use gpt-5-mini vision to identify dish components.

**Stage B — Taste vector generation**: Use the pipeline from Phase 1.1 to generate the 7D taste vector plus richness and texture scores.

**Stage C — Embedding generation**: Generate 768-dim embeddings using `text-embedding-3-large` (with `dimensions=768`). Cost: **$0.065 for 5,000 items**.

**Colombia-specific considerations**:
- Menus are in **Spanish** — both gpt-5-mini and Claude handle Spanish fluently, but prompts should include Spanish culinary vocabulary (e.g., "picante," "almuerzo ejecutivo," "corrientazo")
- Regional dishes (bandeja paisa, sancocho, empanadas, arepas, cholao, lulada) need domain-aware prompting with few-shot examples
- **"Menú del día"** (daily specials) change frequently — the pipeline should support scheduled re-processing

**For physical menus** (important for informal Cali restaurants without delivery presence): Photograph → gpt-5-mini vision → structured JSON. Cost: ~$0.003/image. The open-source OCR system documented on Medium achieves 95%+ accuracy on restaurant menus with 200+ intelligent error corrections.

**Total pipeline cost per 500 items/month**: LLM processing ~$0.10, embeddings ~$0.01. **Negligible.**

**Effort**: 1 week for pipeline; ongoing maintenance for data freshness.

### 3.4 Additional data sources for Latin America

| Source | Coverage | Data Available | Cost | Best For |
|--------|----------|---------------|------|----------|
| **Rappi** | 8 LatAm countries, strong Colombia | Full menus, prices, ratings | $5-10/mo (Apify) | Primary menu data |
| **PedidosYa/DoubleData** | 15 LatAm countries including Colombia | Menus, delivery fees, reviews | Enterprise pricing | Supplementary coverage |
| **Google Places** | Global, good Cali coverage | Restaurant metadata, no menus | Free ($200 credit) | Discovery layer |
| **TripAdvisor Content API** | Global, tourist-oriented | Ratings, rankings, 5 reviews/location | Free (5K calls/mo) | Restaurant ratings |
| **SerpAPI / Serper.dev** | Global | Search results for menu pages | $0.001/search (Serper) | Menu page URLs |

**Not recommended for Cali**: Yelp (minimal LatAm presence), iFood (Brazil-only, exited Colombia), SinglePlatform (US-focused).

---

## Phase 4: Advanced recommendation — hybrid models, personalized explanations, and diversity

These improvements prepare TasteBud for multi-user scaling. **Expected total effort: 4–5 weeks. Monthly API cost: ~$2–5 for explanations.**

### 4.1 LightFM hybrid recommendation engine

**What**: Integrate the **LightFM** library as a hybrid matrix factorization engine that combines collaborative filtering with content features, gracefully handling cold start through feature-based generalization.

**Why LightFM specifically**: It natively supports user and item features (taste vectors, cuisine tags, dietary restrictions), uses **WARP loss** optimized for ranking, and handles cold start — a new user with cuisine preferences but zero interactions still gets meaningful collaborative signal via shared features. It's proven in production, easy to integrate (`pip install lightfm`), and fast.

**Phased hybrid strategy based on user count**:
- **0–100 users**: Pure content-based with Bayesian profiles (Phase 2). LightFM trains on item features only.
- **100–1,000 users**: LightFM hybrid with user features (preferences, demographics) + item features (embeddings, taste vectors, cuisine tags). Feature-based generalization means even 1-interaction users benefit from collaborative signals.
- **1,000–10,000 users**: Blend scores: `(1-confidence)*content_score + confidence*collaborative_score`, where confidence increases with interaction count.
- **10,000+ users**: Graduate to a two-tower model (user tower + item tower, both outputting 128D embeddings, ANN search via FAISS) — the architecture proven at Uber Eats scale.

Uber Eats, DoorDash, and Yelp all converged on similar hybrid architectures. **Yelp's documented approach** — ALS matrix factorization plus XGBoost learning-to-rank on combined content and collaborative features — **doubled** coverage of "tail users" with sparse history. This validates the LightFM-first strategy.

**Effort**: 2 weeks for initial integration + feature engineering. **Python packages**: `lightfm`, `scipy.sparse`.

**Dependencies**: Sufficient user data (Phase 3 pipeline running).

### 4.2 Personalized natural-language explanations

**What**: Replace template-based explanations with LLM-generated personalized explanations that reference the user's specific preferences and history.

**Implementation**: After scoring, pass the top recommendations plus user profile context to gpt-5-mini to generate 1–2 sentence explanations. Use prompt caching to reduce costs (Anthropic's cached reads cost 0.1× base price).

```python
prompt = f"""Explain why '{dish_name}' is recommended for this user:
- They love: {liked_cuisines}
- Recent favorites: {recent_likes}
- This dish scores high on: {top_matching_dimensions}
Write a 1-sentence, conversational explanation. Be specific."""
```

**Cost**: ~$0.002 per explanation (gpt-5-mini). At 50 recommendations/day: **$3/month**.

**Effort**: 3–4 days.

**Dependencies**: 1.1 (LLM pipeline), user profile data.

### 4.3 Diversity mechanisms beyond exploration

**What**: Implement Maximal Marginal Relevance (MMR) to ensure top-K recommendations cover diverse tastes, cuisines, and price points — not just the K highest-scoring items.

```
MMR_score(i) = λ · relevance(i) - (1-λ) · max_j∈selected[sim(i, j)]
```

Start with **λ=0.7** (70% relevance, 30% diversity). Greedily select items one at a time, penalizing similarity to already-selected items.

Additionally, enforce **slot-based diversity**: in a list of 10 recommendations, require at least 2 different cuisines, at least 2 price tiers, and no more than 3 items from the same restaurant.

**Effort**: 2–3 days. **Dependencies**: 1.4 (pre-computed similarity matrix).

### 4.4 Contextual bandits for session optimization

**What**: Formulate each recommendation session as a contextual bandit problem where context = (user profile, time, meal intent, weather, recent history) and actions = recommended items.

**Practical tool**: The `contextualbandits` Python package with `BootstrappedUCB` is the safest starting point — it wraps scikit-learn classifiers and handles the explore-exploit tradeoff automatically. For production scale, **VowpalWabbit** (`vowpalwabbit` package) provides a fast C++ core with streaming updates and is the industry standard (used at Microsoft, Yahoo).

**Effort**: 1–2 weeks. **Dependencies**: 2.1 (exploration framework), sufficient session data.

---

## Phase 5: Production readiness — evaluation, knowledge graphs, and fine-tuned embeddings

These improvements prepare TasteBud for public launch. **Expected total effort: 4–6 weeks. Monthly API cost: stable at ~$5–15.**

### 5.1 Evaluation framework

**What**: Build a three-tier evaluation pipeline: offline metrics, longitudinal tracking, and interleaved comparison.

**Offline metrics** (computed on historical data):
- **NDCG@K**: Measures ranking quality. `DCG@K = Σ (2^rel - 1) / log₂(i+1)`, normalized by ideal ranking.
- **Diversity**: `1 - ILS`, where ILS = average pairwise cosine similarity within recommendation lists.
- **Coverage**: Fraction of catalog ever recommended.
- **Leave-one-out cross-validation**: For each liked item in history, remove it, recompute recommendations, check if it appears in top-K. This is the most reliable single-user offline metric.

**Online metrics to track**:
- **Like ratio**: `likes / (likes + dislikes)` — the core taste accuracy signal
- **Session conversion**: Did the user select something from recommendations?
- **Time to decision**: Lower is better (recommendations are more decisive)
- **Exploration acceptance rate**: Percentage of novel items tried that receive positive feedback

**Single-user evaluation strategy**: Use **temporal split** evaluation — train on history up to time T, test on interactions after T. Slide T forward in a rolling window. Track the rolling 7-day like ratio over time to verify the system is improving.

**Algorithm comparison**: Use **team-draft interleaving** — mix results from two algorithms, track which algorithm's items get selected. Netflix research shows interleaving needs **50–100× fewer samples** than traditional A/B testing. With ~100 sessions, a binomial test can detect meaningful preference differences.

**Python packages**: `evidently` (15+ ranking metrics with visualizations), `recsys_metrics` (PyTorch-based precision/recall/NDCG/diversity), `scipy.stats` (significance testing).

**Effort**: 1–2 weeks. **Dependencies**: Sufficient feedback history.

### 5.2 A/B testing infrastructure for FastAPI

**What**: Lightweight experiment framework with deterministic user-to-variant assignment, event logging, and statistical analysis.

```python
class ABTest:
    def assign(self, user_id: str, experiment: str, variants: list) -> str:
        seed = hashlib.md5(f"{experiment}:{user_id}".encode()).hexdigest()
        bucket = int(seed[:8], 16) / 0xFFFFFFFF
        return variants[int(bucket * len(variants))]
```

**When to use**: After TasteBud goes public with multiple users. For single-user testing, interleaving (5.1) is more efficient.

**Effort**: 2–3 days.

### 5.3 Food knowledge graph (lightweight)

**What**: Build a small knowledge graph in **Neo4j** with nodes (MenuItem, Ingredient, Cuisine, DietaryTag, Restaurant) and relations (CONTAINS_INGREDIENT, BELONGS_TO_CUISINE, SUITABLE_FOR_DIET, SERVED_AT).

**Why**: Enables queries impossible with vector similarity alone: "what vegetarian dishes share ingredients with dishes I've liked?" or "find me something from a cuisine I haven't tried that uses ingredients I enjoy."

**Data sources to populate it**:
- **FlavorDB2** (`cosylab.iiitd.edu.in/flavordb2/`): 25,595 flavor molecules mapped to 936 ingredients. No API, but JSON-formatted data cards can be parsed. Free for non-commercial use.
- **FoodKG** (`foodkg.github.io/`): 67M+ RDF triples combining Recipe1M+, USDA nutritional data, and FoodOn ontology. SPARQL endpoint available.
- **USDA FoodData Central** (`fdc.nal.usda.gov`): REST API with 168 nutrients per food. Python wrapper: `fooddatacentral`.
- LLM-extracted ingredients from Phase 3.3 (the primary practical source for menu items).

**Entity resolution** (mapping "Pan-Seared Salmon with Dill" to database entries): Use embedding similarity between menu item descriptions and food database entries. For 200–5,000 items, manual review of low-confidence matches is feasible.

**Effort**: 2–3 weeks. **Python packages**: `neo4j`, `py2neo`.

### 5.4 Fine-tuned food embeddings

**What**: Fine-tune an open-source embedding model on food-domain data to improve semantic similarity for menu items.

**Why**: Generic embeddings may conflate "Spicy Tuna Roll" with "Tuna Melt" (both contain "tuna" but are vastly different). Domain fine-tuning typically yields **+10–30% improvement** on domain tasks.

**How**: Use `sentence-transformers` with `MatryoshkaLoss` + `MultipleNegativesRankingLoss` on food-specific training pairs. Positive pairs: same-cuisine dishes, flavor variations. Hard negatives: same primary ingredient but different cuisine/style.

**Base model options**:
- **Nomic Embed Text V2**: 768D, MoE architecture (305M active params), Apache 2.0 license, supports Matryoshka truncation to 256D
- **BGE-M3**: Best multilingual option (critical for Spanish menus), supports dense + sparse + multi-vector retrieval

**Data sources for training pairs**: Recipe1M+ dataset, FoodKG recipe co-occurrences, user feedback data (items liked in the same session = positive pair).

**Effort**: 2–3 weeks. **Dependencies**: Sufficient training data (~1,000+ labeled pairs).

---

## Consolidated cost model and dependency map

### Monthly API cost by phase

| Phase | Component | Monthly Cost |
|-------|-----------|-------------|
| 1 | gpt-5-mini taste vectors (500 items) | $0.10 |
| 1 | text-embedding-3-large (500 items) | $0.07 |
| 2 | All local computation | $0.00 |
| 3 | Google Places API | Free ($200 credit) |
| 3 | Rappi data (Apify) | $5–10 |
| 4 | Personalized explanations (50/day) | $3 |
| 5 | Knowledge graph maintenance | $0 |
| **Total at full deployment** | | **$8–14/month** |

The **$15+ budget is more than sufficient** for all phases. The most expensive component is Rappi data access, not LLM calls.

### Critical dependency chain

```
1.1 (LLM taste vectors) → 1.2 (refined dimensions) → 1.3 (population priors)
                                                    → 2.2 (Bayesian profiles)
                                                    → 2.5 (harmony scoring)
1.4 (FAISS activation) → 2.4 (two-stage retrieval)
                       → 4.3 (diversity via MMR)
3.1-3.3 (data pipeline) → 4.1 (LightFM hybrid model)
                        → 5.3 (knowledge graph)
2.2 (Bayesian profiles) → 2.3 (cuisine fix)
                        → 4.4 (contextual bandits)
```

### Impact-prioritized summary of all improvements

The improvements ranked by their direct impact on "does this help the user pick good food faster":

1. **LLM taste vectors** (Phase 1.1) — fixes the core data quality problem everything depends on
2. **Bayesian profiles + Thompson Sampling** (Phase 2.2) — principled learning that adapts fast with minimal data
3. **Population priors** (Phase 1.3) — makes first-session recommendations meaningful instead of random
4. **Exploration bonus** (Phase 2.1) — prevents filter bubbles, one-line code change
5. **Rappi data pipeline** (Phase 3.2) — real menu data for real restaurants in Cali
6. **Two-stage retrieval** (Phase 2.4) — enables "find me something like X" queries
7. **Harmony scoring** (Phase 2.5) — makes multi-course meals genuinely complementary
8. **Dynamic weights** (Phase 2.6) — system self-tunes to what matters for each user
9. **Temporal decay** (Phase 1.5) — prevents stale preferences from haunting recommendations
10. **Cuisine over-penalization fix** (Phase 2.3) — one bad dish no longer kills an entire cuisine
11. **Personalized explanations** (Phase 4.2) — builds trust and teaches users what the system knows
12. **LightFM hybrid model** (Phase 4.1) — collaborative signal when multiple users exist
13. **Diversity mechanisms** (Phase 4.3) — ensures recommendations don't all look the same
14. **Evaluation framework** (Phase 5.1) — required to know if changes actually help

---

## Conclusion: where this plan leaves TasteBud

The most striking finding across all research streams is how cheaply modern LLMs solve TasteBud's most painful problems. The manual taste vector bottleneck — the system's biggest weakness — disappears for $0.04 per 200 items. The cold start problem, which plagues even billion-dollar platforms, becomes manageable through Bayesian priors and a 30-second onboarding flow. And the exploration-exploitation tradeoff, historically a complex engineering challenge, reduces to replacing point-estimate taste vectors with Beta distributions and sampling from them.

The architecture proven at Uber Eats, DoorDash, and Yelp — embedding retrieval → feature-based reranking → hybrid collaborative/content scoring — is now accessible at indie-developer scale. LightFM provides the hybrid engine. FAISS handles retrieval for free. gpt-5-mini handles all the NLP-heavy lifting at fractions of a cent. The primary constraint isn't compute or API budget — it's **menu data access in Cali**, which Rappi solves as the dominant local platform.

The phased approach means TasteBud can ship meaningful improvements within the first week (LLM vectors + exploration bonus + temporal decay) while building toward a production-grade system over 4–5 months. The transition from "works for me" to "works for everyone" is primarily a data pipeline and evaluation problem — not an algorithmic one. The algorithms are ready; the food science is well-understood; the tools are cheap and mature. What remains is systematic execution.