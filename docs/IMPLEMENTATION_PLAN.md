# TasteBud Recommendation System Enhancement - Implementation Plan

**Created**: February 11, 2026  
**Status**: Phase 1 In Progress  
**Focus**: Single-user recommendation quality improvements

---

## Overview

This plan systematically upgrades TasteBud's recommendation algorithm from a functional prototype to a production-grade system. The approach is to fix known issues, activate dormant features, and implement scientifically-backed learning mechanisms - all while maintaining the existing architecture's strengths.

**Current Architecture Strengths**:
- ✅ FAISS integration complete and performant
- ✅ Multi-service clean separation of concerns
- ✅ Comprehensive feedback collection system
- ✅ Type-safe Pydantic models throughout
- ✅ PDF ingestion pipeline functional

**Known Issues to Address**:
- ❌ Uncertainty vector tracked but never used for exploration
- ❌ LLM taste vectors generated but keyword-based used as primary
- ❌ Flat 0.5 cold start priors produce random first recommendations
- ❌ No temporal decay - 6-month-old feedback weighs same as yesterday's
- ❌ One bad dish tanks entire cuisine affinity

---

## Phase 1: Foundation Fixes (Current)

**Goal**: Fix the four most damaging issues affecting every recommendation.

**Expected Impact**: +15-25% improvement in first-session like ratio, better diversity, faster learning.

**Estimated Effort**: 2-3 weeks per step, but no time constraints per project requirements.

### Step 1.1: LLM-Generated Taste Vectors as Primary Source

**Problem**: `services/llm_features.py` generates quality taste vectors via GPT-5-mini, but `services/features.py` uses unreliable keyword matching as primary method.

**Solution**:
1. Invert priority in `build_item_features()`: LLM-first, keywords fallback
2. Cache LLM results in `MenuItem.provenance` to avoid regeneration
3. Update ingestion pipeline to always call LLM taste profile generation
4. Create batch regeneration script for existing items
5. Enhanced prompt for 7D schema

**Files to modify**:
- `services/features.py` - Change `build_item_features()` priority
- `services/ingestion/ingestion_orchestrator.py` - Always call LLM
- `services/llm_features.py` - Update prompt for 7D + richness
- `scripts/regenerate_taste_vectors_llm.py` - New batch script

**Cost**: $0.04 per 200 items with gpt-5-mini

**Validation**:
- Compare LLM vs keyword results on 20 sample items
- Verify cache hits on second ingestion
- Check LLM call logs show expected usage

### Step 1.2: Refined Taste Vector Dimensions

**Problem**: Current 10D vector has redundant axes (sour/acidity are same) and mixes taste/texture modalities.

**Solution**: Migrate to scientifically-grounded 7D taste vector:
- **Taste (7D)**: `[sweet, sour, salty, bitter, umami, fatty, spicy]`
- **Texture (3D)**: `[crunchy, creamy, chewy]` - separate optional vector
- **Richness (1D)**: scalar for meal composition

**Scientific basis**:
- Five basic tastes are established science
- Fat taste (oleogustus) gaining acceptance as sixth
- Spicy is pain signal (TRPV1) but essential for food recommendation
- Texture is separate sensory modality - shouldn't distort taste similarity

**Files to modify**:
- `models/user.py` - Update `TASTE_AXES` constant
- `models/restaurant.py` - Add texture + richness fields to MenuItem
- `services/llm_features.py` - Update prompt to return 7D + texture + richness
- `services/reranking_service.py` - Update scoring to use 7D
- `services/unified_feedback_service.py` - Update all vector operations
- `services/online_learning_service.py` - Update feedback processing
- `scripts/migrate_taste_dimensions_7d.py` - New migration script

**Migration strategy**:
- Map old→new: drop `acidity`, average `temp_hot` into `spicy`, extract `crunch` to texture
- Zero-fill richness initially (will be populated by LLM regeneration)
- Preserve all user history

**Validation**:
- All users have 7D taste_vector after migration
- All items have 7D features after regeneration
- Cosine similarity calculations work with new dimensions

### Step 1.3: Population-Based Cold Start Priors

**Problem**: New users start with flat 0.5 across all dimensions, producing effectively random recommendations in first session.

**Solution**: K-Means clustering of existing items into 6 taste archetypes. During onboarding, 3-question flow identifies closest archetype. Initialize user profile with archetype centroid instead of flat 0.5.

**Archetype examples**:
- Comfort Food Lover: High fatty, moderate sweet, low spicy
- Spice Adventurer: High spicy, high umami, variable other
- Health Conscious: Low fatty, high sour/bitter, high vegetable affinity
- Sweet Tooth: High sweet, moderate fatty
- Savory Explorer: High umami, salty, fatty
- Balanced Palate: All dimensions near 0.5 (current default as fallback)

**Files to modify**:
- `models/user.py` - Add `taste_archetype_id: Optional[UUID]`
- `models/population.py` - New `TasteArchetype(id, name, taste_vector, description)` model
- `services/onboarding_service.py` - Update to use archetypal initialization
- `services/archetype_service.py` - New service for archetype management
- `scripts/cluster_taste_archetypes.py` - New clustering script

**Clustering approach**:
```python
from sklearn.cluster import KMeans
import numpy as np

# Collect all item taste vectors
item_vectors = [item.features for item in all_items]

# K-Means clustering
kmeans = KMeans(n_clusters=6, random_state=42, n_init=20)
kmeans.fit(item_vectors)

# Label clusters manually by inspecting centroids
archetypes = [
    {"name": "Comfort Food Lover", "centroid": kmeans.cluster_centers_[0]},
    # ... label others
]
```

**Onboarding questions**:
1. "Which sounds most appealing right now?" (4 options from different archetypes)
2. "How adventurous are you with spicy food?" (Scale 1-5)
3. "Sweet or savory?" (Binary choice with intensity)

**Validation**:
- New users get archetype-based initialization
- First recommendations should cluster around archetype characteristics
- Track first-session like ratio improvement

### Step 1.4: Exploration Bonus Using Uncertainty Vector

**Problem**: `taste_uncertainty` tracked but never used in scoring. System gets stuck in filter bubbles.

**Solution**: Add exploration term to scoring formula that boosts items strong in uncertain taste dimensions.

**Modified scoring**:
```python
exploration_bonus = EXPLORATION_COEFFICIENT * dot(user.uncertainty, abs(item.features))
base_score = taste_similarity + cuisine_bonus + popularity + exploration_bonus
```

**Rationale**: Item with high spicy (0.9) gets boosted when user's spicy uncertainty is high (0.5), encouraging exploration. As user provides feedback, uncertainty decreases, exploration naturally decays.

**Files to modify**:
- `config/settings.py` - Add `EXPLORATION_COEFFICIENT: float = 0.2`
- `services/reranking_service.py` - Add exploration term to scoring
- `services/explanation_service.py` - Log exploration score component

**Parameter tuning**: Start with 0.2, can be personalized later. Higher = more exploration, lower = more exploitation.

**Validation**:
- Recommendations should include some high-uncertainty items
- Diversity metrics should improve
- Track exploration acceptance rate (novel items that get liked)

### Step 1.5: Temporal Feedback Decay

**Problem**: Dislike from 6 months ago carries same weight as like from yesterday. Preferences drift over time.

**Solution**: Apply exponential decay with 21-day half-life to all feedback processing.

**Decay formula**:
```python
weight = 0.5 ** (days_elapsed / HALF_LIFE_DAYS)
```

**Half-life selection**: 21 days chosen because:
- Food preferences are relatively stable (unlike fashion)
- Seasonal changes matter (summer→winter food shifts)
- Life events affect tastes (pregnancy, illness, etc.)
- After 3 months (≈4 half-lives), weight ≈ 0.06 (minimal but present)

**Files to modify**:
- `config/settings.py` - Add `FEEDBACK_HALF_LIFE_DAYS: int = 21`
- `services/unified_feedback_service.py` - Add `temporal_weight()` function
- `services/online_learning_service.py` - Apply decay to post-meal updates
- `scripts/recompute_profiles_with_decay.py` - Recalculate existing profiles

**Implementation**:
```python
def temporal_weight(feedback_time: datetime, half_life_days: int) -> float:
    if not feedback_time:
        return 1.0
    delta_days = (datetime.utcnow() - feedback_time).total_seconds() / 86400
    return 0.5 ** (delta_days / half_life_days)
```

**Apply to**:
- Taste vector updates
- Cuisine affinity updates
- Ingredient preference updates

**Validation**:
- Recent feedback should dominate profile
- Old preferences should fade but not disappear
- Profile should adapt faster to new patterns

---

## Phase 2: Intelligent Learning (Next)

**Goal**: Replace point-estimate profiles with Bayesian distributions, fix cuisine over-penalization, improve harmony scoring.

### Step 2.1: Bayesian Taste Profiles with Thompson Sampling
- Model each taste dimension as Beta(α, β) distribution
- Thompson Sampling naturally balances exploration/exploitation
- Eliminates need for separate uncertainty tracking

### Step 2.2: Fix Cuisine Over-Penalization
- Convert cuisine affinity to Bayesian Beta parameters
- Weight updates by cuisine typicality (fusion dishes matter less)

### Step 2.3: Enhanced Harmony Scoring
- Implement three harmony dimensions: contrast, intensity arc, diversity
- Based on flavor science research

### Step 2.4: Dynamic Weight Learning
- Learn scoring weights from user feedback
- Online gradient descent + periodic Optuna optimization

### Step 2.5: Pre-compute Similarity Matrix
- N×N cosine similarity matrix for O(1) harmony lookups

---

## Phase 3: Two-Stage Retrieval & Diversity

**Goal**: Enable query-based recommendations, ensure diversity.

### Step 3.1: Two-Stage Retrieval Pipeline
- Stage 1: FAISS top-30 by embedding
- Stage 2: Feature-based reranking
- Support query modifiers ("like X but spicier")

### Step 3.2: Enhanced MMR
- Configurable diversity level per request
- Slot-based constraints (cuisines, prices, restaurants)

### Step 3.3: Cross-Encoder Re-Ranker (Optional)
- For query-based searches only
- Benchmark latency before deployment

---

## Phase 4: Explanations & Evaluation

**Goal**: Build trust through better explanations, measure system performance.

### Step 4.1: Personalized LLM Explanations
- LLM-first (not fallback)
- Reference user's specific history
- Prompt caching for cost reduction

### Step 4.2: Evaluation Framework
- Offline metrics: nDCG@K, diversity, coverage
- Online metrics: like ratio, time to decision
- Temporal split evaluation

### Step 4.3: Team-Draft Interleaving
- Algorithm comparison with 50-100 samples
- Statistical significance testing

---

## Phase 5: Production Readiness

**Goal**: Observability, automated maintenance, resilience.

### Step 5.1: Index Maintenance Automation
- Scheduled nightly rebuilds
- On-demand rebuild endpoint
- Incremental updates for new items

### Step 5.2: Structured Logging & Observability
- Correlation ID propagation
- Stage-level timing metrics
- Optional Prometheus integration

### Step 5.3: Configuration Management
- Audit hardcoded parameters
- YAML config files with validation
- Runtime config reload

### Step 5.4: Error Handling & Resilience
- Comprehensive fallback chains
- Circuit breaker for external APIs
- Health check endpoints

---

## Dependencies & Critical Path

```
Phase 1.1 + 1.2 → All downstream feature engineering
Phase 1.3 → Better onboarding experience
Phase 1.4 → Diversity improvements
Phase 1.5 → Phase 2.1 (Bayesian profiles)

Phase 2.1 → Phase 2.2, 2.4
Phase 2.3 + 2.5 → Multi-course quality

Phase 3.1 → Phase 3.2, 3.3

Phase 4.2 → Phase 4.3

Phase 5 steps can proceed in parallel
```

---

## Success Metrics

**Phase 1 Success Criteria**:
- [ ] First-session like ratio improves by 15%+
- [ ] LLM taste vectors used for 100% of new items
- [ ] Exploration items appear in every top-10 list
- [ ] Recent feedback dominates profile updates
- [ ] New users get archetypal initialization

**Phase 2 Success Criteria**:
- [ ] Overall like ratio improves by 20%+
- [ ] Cuisine affinity recovers from single bad experience
- [ ] Multi-course meals show improved harmony
- [ ] Uncertainty decreases with each interaction
- [ ] Weights personalize per user

**Phase 3 Success Criteria**:
- [ ] Query-based searches work ("something spicy")
- [ ] Diversity score increases by 25%+
- [ ] FAISS retrieval stays under 50ms
- [ ] Top-10 lists satisfy diversity constraints

**Phase 4 Success Criteria**:
- [ ] nDCG@10 tracked over time
- [ ] Explanations reference user history
- [ ] Statistical comparison framework functional
- [ ] Coverage reaches 80%+ of catalog

**Phase 5 Success Criteria**:
- [ ] Zero manual index rebuilds needed
- [ ] All recommendation requests have correlation IDs
- [ ] Fallback chains prevent outages
- [ ] Health checks pass continuously

---

## Cost Projections

| Phase | Component | Monthly Cost |
|-------|-----------|--------------|
| 1 | LLM taste vectors (500 items/month) | $0.10 |
| 1 | Embeddings (500 items/month) | $0.07 |
| 2-3 | All local computation | $0.00 |
| 4 | LLM explanations (50/day) | $3.00 |
| **Total** | | **~$3.20/month** |

Current budget allows extensive experimentation with no cost concerns.

---

## Clean Code Compliance

This implementation follows all project clean code guidelines:

**Structural**:
- ✅ Single responsibility per function
- ✅ Self-documenting code (no comments/docstrings)
- ✅ Pydantic models for all data structures
- ✅ Type hints on all signatures
- ✅ Enums for fixed value sets

**Data Handling**:
- ✅ No result dictionaries with success flags
- ✅ Exceptions for errors, return data for success
- ✅ Structured types over dictionaries
- ✅ Modern Python features (3.10+)

**Safety**:
- ✅ Fail fast - validate before processing
- ✅ No default values for required config
- ✅ Domain-specific exceptions
- ✅ Temporal tracking for all feedback

**Operations**:
- ✅ Structured logging with correlation IDs
- ✅ Dependencies injected, not global
- ✅ Atomic commits per logical change
- ✅ Migration scripts for schema changes

---

## Current Status

**Phase**: 1 (Foundation Fixes)  
**Step**: Starting implementation  
**Started**: February 11, 2026  
**Next Review**: After Step 1.1 completion

Progress tracking via todo list system and git commits.
