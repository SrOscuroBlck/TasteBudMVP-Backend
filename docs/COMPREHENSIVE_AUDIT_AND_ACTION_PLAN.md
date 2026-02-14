# TasteBud Backend: Comprehensive Audit & Action Plan

**Date**: February 14, 2026  
**Status**: 🔴 CRITICAL ISSUES IDENTIFIED - Immediate Action Required

---

## Executive Summary

After comprehensive code audit, I've identified **critical bugs preventing the recommendation system from functioning correctly**, plus significant gaps between what was documented in Phase 1-5 completion docs versus what was actually implemented.

### 🚨 Critical Findings

1. **PRIMARY BUG**: Missing `flag_modified()` calls causing session exclusions to never persist to database
2. **IMPLEMENTATION GAPS**: Phases 1-5 were partially implemented - many claimed features don't exist or don't work
3. **CODEBASE CHAOS**: 40+ service files with no organization, duplicate logic, unclear separation of concerns
4. **NO WORKING DIVERSITY**: Despite Phase 3 claiming MMR implementation, recommendations are deterministic and repetitive

### Impact on User Experience

**Current Symptom**: "I click dislike, next recommendations show same items in exact same order"

**Why This Happens**:
- Session exclusions never save to database (Bug #1)
- Scoring is completely deterministic (Bug #4)
- No randomization or diversity mechanisms
- Filtering logic has multiple failure points

---

## Part 1: Critical Bugs (Immediate Fixes Required)

### Bug #1: Missing flag_modified() for JSON Columns 🚨 HIGHEST PRIORITY

**Location**: `services/session_service.py` lines 172-183, 156-168  
**Severity**: CRITICAL  
**Impact**: Session-level exclusions NEVER persist to database

**The Problem**:
```python
def add_excluded_item(self, db_session: Session, session_id: UUID, item_id: UUID):
    session = self.get_session(db_session, session_id)
    if str(item_id) not in session.excluded_items:
        session.excluded_items = session.excluded_items + [str(item_id)]
        db_session.add(session)
        db_session.commit()
        # ❌ MISSING: flag_modified(session, "excluded_items")
```

**Why It Fails**:
- SQLAlchemy doesn't automatically track mutations to JSON columns
- The commit() silently fails to persist the change
- Next request loads OLD data from DB without the exclusion
- Item appears again

**Fix Required**:
```python
from sqlalchemy.orm.attributes import flag_modified

def add_excluded_item(self, db_session: Session, session_id: UUID, item_id: UUID):
    session = self.get_session(db_session, session_id)
    if str(item_id) not in session.excluded_items:
        session.excluded_items = session.excluded_items + [str(item_id)]
        flag_modified(session, "excluded_items")  # ✅ ADD THIS
        db_session.add(session)
        db_session.commit()
```

**Same bug in**: `add_items_shown()` at line 165

---

### Bug #2: Completely Deterministic Scoring

**Location**: `services/recommendation_service.py` lines 600-720  
**Severity**: HIGH  
**Impact**: Given same user + items, ALWAYS produces same order

**The Problem**:
```python
# No randomization anywhere in final ranking
base_scores: Dict[str, float] = {}
for it in candidates:
    s = cosine_similarity(adjusted_taste_vector, it.features)  # Deterministic
    s += cuisine_bonus  # Deterministic
    s += popularity_score  # Deterministic
    base_scores[str(it.id)] = s

# Deterministic sort - always same order
sorted_items = sorted(candidates, key=lambda it: base_scores[str(it.id)], reverse=True)
return sorted_items[:top_n]
```

**Why It Fails**:
- Thompson Sampling provides some randomization in `adjusted_taste_vector`
- BUT if user profile hasn't been updated, sampled values are similar
- Final ranking is pure deterministic sort of those scores
- No tie-breaking randomization
- No diversity mechanisms (MMR documented but not actually used in main flow)

**Fix Required**:
1. Add tie-breaking randomization to final sort
2. Actually use MMR for diversity (documented in Phase 3, exists in code but NOT integrated)
3. Add epsilon-greedy exploration

---

### Bug #3: Type Annotation Mismatch

**Location**: `models/session.py` line 53  
**Severity**: MEDIUM  
**Impact**: Model lies about data type, may cause serialization issues

```python
# Model says:
excluded_items: List[UUID] = Field(...)

# Code actually stores:
session.excluded_items = session.excluded_items + [str(item_id)]  # List[str]
```

**Fix**: Change type annotation to `List[str]`

---

### Bug #4: Insufficient Logging

**Location**: Multiple locations in recommendation flow  
**Severity**: MEDIUM  
**Impact**: Impossible to debug filtering failures in production

**Missing Logs**:
- No log when session exclusion filtering happens
- Permanent exclusion filtering only at DEBUG level
- No summary of "X items filtered, Y items shown"
- No verification that filtering worked

**Fix Required**: Add INFO-level logging at all filtering points with counts

---

### Bug #5-8: See RECOMMENDATION_FILTERING_ANALYSIS.md

Additional bugs documented in detail in the filtering analysis document.

---

## Part 2: Phase Implementation Gaps

### Phase 1: Foundation Fixes

**Claimed**: "All 5 steps implemented and tested"  
**Reality**: Partially implemented

#### ✅ What Actually Works:
- TASTE_AXES reduced to 7D (correct)
- TEXTURE_AXES separated (correct)
- BayesianTasteProfile model exists with Thompson Sampling
- temporal_weight() function exists
- Archetypes models exist

#### ❌ What Doesn't Work or Is Missing:
1. **LLM taste vectors as primary**: Code still has keyword fallback logic everywhere, unclear if LLM is actually primary
2. **Temporal decay**: Function exists but NOT INTEGRATED into profile updates - commented code exists but not active
3. **Exploration bonus**: Code exists in old `_calculate_exploration_bonus()` but NOT USED in current pipeline
4. **Archetype initialization**: Service exists but NOT INTEGRATED into onboarding flow
5. **Migration scripts**: Exist but unclear if ever run - user data may still be in 10D format

**Gap Severity**: MEDIUM - Features partially implemented but not integrated or activated

---

### Phase 2: Bayesian Profiles & Intelligent Learning

**Claimed**: "All 5 steps implemented and tested"  
**Reality**: Core infrastructure exists but incomplete integration

#### ✅ What Actually Works:
- BayesianTasteProfile model with alpha/beta parameters
- sample_taste_preferences() method working
- Thompson Sampling integrated in `recommend_with_session`
- Bayesian updates in `bayesian_profile_service.py`

#### ❌ What Doesn't Work or Is Missing:
1. **Cuisine typicality**: LLM doesn't return typicality scores (Phase 2 claim)
2. **Harmony scoring**: HarmonyService exists but NOT USED in meal composition
3. **Weight learning**: UserScoringWeights model exists but service not integrated
4. **Similarity matrix**: SimilarityMatrixService exists but not pre-computed or loaded
5. **Dynamic weights**: Optuna integration code exists but never runs

**Gap Severity**: MEDIUM-HIGH - Core Bayesian system works but advanced features missing

---

### Phase 3: Two-Stage Retrieval & Diversity

**Claimed**: "All 3 steps implemented and tested"  
**Reality**: Query parsing exists, diversity NOT actually used

#### ✅ What Actually Works:
- QueryParsingService exists and parses queries
- QueryModifier enums defined
- retrieve_candidates_from_query() works
- MMRService class exists with rerank_with_mmr() method
- CrossEncoderService exists

#### ❌ What Doesn't Work or Is Missing:
1. **MMR NOT USED in main flow**: recommend_with_session() does NOT call MMR - just deterministic sort
2. **MMR only used in query-based recommendations**: recommend_from_query() uses it, but main API doesn't
3. **Diversity constraints**: DiversityConstraints model exists but never populated or used
4. **Cross-encoder**: Exists but disabled by default, unclear if ever tested

**Gap Severity**: HIGH - Major claimed feature (diversity) NOT in production path

---

### Phase 4: Explanations & Evaluation

**Claimed**: "All 3 steps implemented and tested"  
**Reality**: Services exist but minimal integration

#### ✅ What Actually Works:
- PersonalizedExplanationService exists
- EvaluationMetric models exist
evaluation_metrics_service.py exists
- TeamDraftInterleavingService exists

#### ❌ What Doesn't Work or Is Missing:
1. **Personalized explanations NOT USED**: recommend_with_session() still uses old explanation_service.py
2. **No evaluation running**: Scripts exist but no evidence of actual evaluation data
3. **No A/B testing active**: TDI service exists but no active experiments
4. **Metrics not collected**: Models exist but no cron jobs or collection active

**Gap Severity**: LOW-MEDIUM - Infrastructure exists, just not operationalized

---

### Phase 5: Production Readiness

**Claimed**: "All 4 steps implemented and tested"  
**Reality**: Some services exist, not integrated

#### ✅ What Actually Works:
- IndexMaintenanceService exists
- Admin endpoints exist (admin_index.py, admin_rebuild.py)
- ConfigLoader appears to work
- Health check endpoint exists

#### ❌ What Doesn't Work or Is Missing:
1. **No scheduled maintenance running**: ScheduledIndexMaintenance exists but not activated in main.py
2. **No correlation ID propagation**: Middleware exists but unclear if actually added to app
3. **No Prometheus metrics**: utils/prometheus_metrics.py missing entirely
4. **Config validation**: Script exists but config.yaml uses settings.py instead

**Gap Severity**: LOW - Production features nice-to-have but not critical for core functionality

---

## Part 3: Codebase Organization Issues

### Current Chaos: 40+ Service Files, No Structure

```
services/
├── archetype_service.py
├── auth_service.py
├── bayesian_profile_service.py
├── confidence_service.py
├── context_enhancement_service.py
├── cross_encoder_service.py
├── email_followup_service.py
├── email_service.py
├── embedding_service.py
├── evaluation_metrics_service.py
├── explanation_enhancement_service.py
├── explanation_service.py              # OLD - still used
├── personalized_explanation_service.py # NEW - not used
├── faiss_service.py
├── features.py
├── gpt_helper.py
├── harmony_service.py                  # Exists but NOT USED
├── in_session_learning_service.py
├── index_maintenance_service.py
├── interaction_history_service.py
├── llm_features.py
├── meal_composition_service.py
├── menu_service.py
├── ml_reranking_service.py
├── mmr_service.py                      # Exists but NOT USED in main flow
├── onboarding_service.py
├── online_learning_service.py
├── query_service.py
├── rating_reminder_service.py
├── recommendation_service.py           # 810 lines - God object
├── reranking_service.py
├── retrieval_service.py
├── scheduled_maintenance.py
├── session_service.py
├── similarity_matrix_service.py         # NOT USED
├── team_draft_interleaving_service.py   # NOT USED
├── umap_reducer.py
├── unified_feedback_service.py
├── weight_learning_service.py           # NOT USED
└── ingestion/
    ├── (ingestion-related services)
```

### Problems:

1. **No Separation of Concerns**: Everything flat in one folder
2. **Duplicate Services**: Two explanation services, unclear which is used
3. **God Object**: recommendation_service.py is 810 lines with multiple responsibilities
4. **Dead Code**: Many services exist but are never called
5. **Unclear Dependencies**: No clear import hierarchy or layering

---

## Part 4: Scripts folder Chaos

### Current State: 32 Scripts, Mixed Purposes

```
scripts/
├── analyze_ab_test.py
├── bootstrap_ratings_from_onboarding.py
├── bootstrap_taste_profile.py
├── build_faiss_index.py
├── build_similarity_matrix.py
├── cluster_taste_archetypes.py
├── compute_online_metrics.py
├── create_evaluation_tables.py
├── generate_embeddings.py
├── migrate_add_course_cuisine.py
├── migrate_add_feedback_indexes.py
├── migrate_add_permanently_excluded_items.py
├── migrate_composition_feedback.py
├── migrate_fix_permanently_excluded_items_type.py
├── migrate_taste_dimensions_7d.py
├── migrate_to_bayesian_profiles.py
├── populate_features.py
├── process_rating_reminders.py
├── recompute_profiles_with_decay.py
├── regenerate_features_smart.py
├── regenerate_taste_vectors_llm.py
├── reset_user.py
├── run_offline_evaluation.py
├── smoke_gpt_flow.py
├── test_course_filtering.py             # TEST
├── test_mmr_diversity.py                # TEST
├── test_mvp_endpoints.sh                # TEST
├── test_pdf_ingestion.py                # TEST
├── test_pdf_ingestion_detailed.py       # TEST
├── test_query_recommendations.py        # TEST
├── train_reranker.py
└── validate_config.py
```

### Problems:

1. **Tests Mixed With Scripts**: 6 test files in scripts folder - should be in tests/
2. **Many Migrations**: 6 migration scripts - should migrations be in alembic?
3. **Unclear Which Are Production**: Which scripts should run in prod vs dev only?
4. **No Documentation**: No README explaining what each script does
5. **Shell Scripts**: test_mvp_endpoints.sh doesn't follow Python patterns

---

## Part 5: Priority Actions Required

### 🔴 P0: Critical Bug Fixes (Do Immediately)

**Timeline**: 1-2 days

1. **Fix flag_modified() bug in session_service.py**
   - Lines: 165, 181
   - Add `flag_modified(session, "excluded_items")` and `flag_modified(session, "items_shown")`
   - Test: Verify exclusions persist across requests

2. **Add randomization to ranking**
   - Location: recommendation_service.py line 718
   - Add epsilon-greedy or tie-breaking randomization
   - Add MMR integration to recommend_with_session()

3. **Fix type annotations**
   - models/session.py line 53: Change `List[UUID]` to `List[str]`

4. **Add filtering verification logging**
   - Log counts at INFO level
   - Log each exclusion point with item counts

**Acceptance Criteria**:
- User clicks DISLIKE → Item never appears again in that session
- Recommendations have some variation even without new feedback
- Logs show "Filtered X items, showing Y items"

---

### 🟠 P1: Integration of Existing Features

**Timeline**: 3-5 days

1. **Integrate MMR into main recommendation flow**
   - Currently only used in query-based recommendations
   - Add MMR call to recommend_with_session()
   - Configure diversity_weight parameter (start with 0.3)

2. **Activate PersonalizedExplanationService**
   - Replace explanation_service calls with personalized version
   - Test user history integration

3. **Integrate temporal decay into profile updates**
   - Code exists but commented out
   - Activate in unified_feedback_service

4. **Add similarity matrix pre-computation**
   - Run build_similarity_matrix.py
   - Load at app startup
   - Use in MMR calculations

**Acceptance Criteria**:
- Recommendations show diversity (not all from same cuisine/restaurant)
- Explanations reference user's specific history
- Old feedback has less weight than recent feedback
- Similarity lookups are O(1)

---

### 🟡 P2: Code Organization & Cleanup

#### Reorganize services folder:

```
services/
├── core/
│   ├── recommendation_service.py
│   ├── retrieval_service.py
│   ├── reranking_service.py
│   └── session_service.py
├── learning/
│   ├── bayesian_profile_service.py
│   ├── unified_feedback_service.py
│   ├── online_learning_service.py
│   ├── in_session_learning_service.py
│   └── weight_learning_service.py
├── features/
│   ├── features.py
│   ├── llm_features.py
│   ├── embedding_service.py
│   └── faiss_service.py
├── user/
│   ├── auth_service.py
│   ├── onboarding_service.py
│   ├── interaction_history_service.py
│   └── archetype_service.py
├── explanation/
│   ├── explanation_service.py (rename OLD to legacy)
│   ├── personalized_explanation_service.py
│   └── explanation_enhancement_service.py
├── composition/
│   ├── meal_composition_service.py
│   ├── harmony_service.py
│   └── query_service.py
├── diversity/
│   ├── mmr_service.py
│   └── cross_encoder_service.py
├── ml/
│   ├── ml_reranking_service.py
│   └── umap_reducer.py
├── evaluation/
│   ├── evaluation_metrics_service.py
│   ├── team_draft_interleaving_service.py
│   └── confidence_service.py
├── infrastructure/
│   ├── index_maintenance_service.py
│   ├── scheduled_maintenance.py
│   └── similarity_matrix_service.py
├── context/
│   ├── context_enhancement_service.py
│   └── menu_service.py
├── communication/
│   ├── email_service.py
│   ├── email_followup_service.py
│   └── rating_reminder_service.py
└── ingestion/
    └── (existing ingestion services)
```

#### Reorganize scripts folder:

```
scripts/
├── migrations/
│   ├── migrate_*.py (all 6 scripts)
│   └── README.md (explain each migration)
├── data_generation/
│   ├── generate_embeddings.py
│   ├── build_faiss_index.py
│   ├── build_similarity_matrix.py
│   ├── cluster_taste_archetypes.py
│   └── populate_features.py
├── maintenance/
│   ├── regenerate_features_smart.py
│   ├── regenerate_taste_vectors_llm.py
│   ├── recompute_profiles_with_decay.py
│   └── process_rating_reminders.py
├── onboarding/
│   ├── bootstrap_ratings_from_onboarding.py
│   └── bootstrap_taste_profile.py
├── evaluation/
│   ├── run_offline_evaluation.py
│   ├── analyze_ab_test.py
│   ├── compute_online_metrics.py
│   └── train_reranker.py
├── admin/
│   ├── reset_user.py
│   └── validate_config.py
├── dev/
│   └── smoke_gpt_flow.py
└── README.md (document all scripts)

# Move tests to proper location:
tests/
├── integration/
│   ├── test_pdf_ingestion.py
│   ├── test_pdf_ingestion_detailed.py
│   ├── test_query_recommendations.py
│   └── test_mvp_endpoints.py (convert from .sh)
└── unit/
    ├── test_mmr_diversity.py
    └── test_course_filtering.py
```

**Acceptance Criteria**:
- Services organized by domain/responsibility
- Clear folder structure
- No duplicate services
- Tests in tests/ folder
- Scripts documented in README

---

### 🟢 P3: Operationalize Evaluation & Monitoring

1. **Set up evaluation pipeline**
   - Run offline evaluation weekly
   - Track metrics over time
   - Create dashboard

2. **Activate A/B testing**
   - Set up TDI experiments
   - Compare algorithms
   - Make data-driven decisions

3. **Add monitoring**
   - Correlation ID middleware
   - Prometheus metrics
   - Alert on errors

4. **Scheduled maintenance**
   - Activate nightly index rebuilds
   - Profile recomputation jobs
   - Matrix rebuilds

**Acceptance Criteria**:
- Metrics dashboard showing like ratio, diversity, coverage
- At least one A/B test running
- Monitoring showing request latencies and error rates
- Automated maintenance running

---

## Part 6: Documentation Debt

### What Exists But Is Misleading:

1. **Phase completion docs (PHASE_1-5_COMPLETE.md)**
   - Claim features are "implemented and tested"
   - Reality: Many features partially implemented or not integrated
   - **Action**: Update docs with actual status, mark TODOs

2. **IMPLEMENTATION_PLAN.md**
   - Good high-level plan
   - Doesn't match actual implementation state
   - **Action**: Update with gaps identified

3. **No service documentation**
   - 40 service files, unclear which do what
   - No docstrings (clean code guidelines say avoid them)
   - **Action**: Add README.md in services/ explaining architecture

4. **No API documentation**
   - OpenAPI/Swagger exists but incomplete
   - **Action**: Complete API docs

---

## Part 7: Testing Status

### What Exists:
- 6 test scripts in scripts/ folder
- Some integration tests

### What's Missing:
- **Unit tests** for core services
- **Integration tests** for full recommendation flow
- **Test coverage tracking**
- **CI/CD pipeline** running tests

### Recommended:
1. Move tests to tests/ folder
2. Add pytest configuration
3. Write unit tests for:
   - Filtering logic
   - Bayesian updates
   - MMR diversity
   - Session exclusion
4. Set up CI to run tests on PR

---

## Part 8: Technical Debt Summary

### Code Quality:
- **God Objects**: recommendation_service.py (810 lines)
- **Duplicate Logic**: Two explanation services, multiple filtering implementations
- **Dead Code**: Services that exist but are never called
- **Type Safety**: Type annotations don't match actual data

### Architecture:
- **Unclear Layering**: Services call services in circular ways
- **Mixed Responsibilities**: recommendation_service does retrieval, ranking, explanation, composition
- **No Interfaces**: Services tightly coupled

### Testing:
- **Low Coverage**: Core logic untested
- **Integration Tests Missing**: Full flow not tested
- **No Regression Tests**: Bug fixes not captured in tests

### Operations:
- **No Monitoring**: Can't see what's happening in production
- **No Evaluation**: Don't know if recommendations are good
- **Manual Maintenance**: No automation for rebuilds

---

## Part 9: Immediate Next Steps

1. Fix flag_modified() bug (30 minutes)
2. Add logging to filtering (30 minutes)
3. Fix type annotation (15 minutes)
4. Test that exclusions now work (1 hour)
5. Deploy fix (30 minutes)

1. Integrate MMR into main flow (4 hours)
2. Add tie-breaking randomization (2 hours)
3. Activate personalized explanations (3 hours)
4. Run similarity matrix pre-computation (1 hour)
5. Test diversity improvements (2 hours)


1. Reorganize codebase (3-4 days)
2. Write unit tests (2-3 days)
3. Update documentation (1 day)
4. Code review and refinement (1 day)

---

## Part 10: Success Metrics

### Before Fixes:
- ❌ Disliked items reappear
- ❌ Recommendations always same order
- ❌ No diversity in results
- ❌ Can't debug filtering issues

### After P0 Fixes:
- ✅ Disliked items never reappear in session
- ✅ Recommendations have variation
- ✅ Can see filtering in logs

### After P1 Integration:
- ✅ Diverse recommendations (cuisines, restaurants)
- ✅ Personalized explanations with user history
- ✅ Old feedback has less influence

### After P2 Cleanup:
- ✅ Clear code organization
- ✅ Easy to find specific logic
- ✅ Tests in proper location
- ✅ Documentation matches reality

### After P3 Operationalization:
- ✅ Monitoring dashboard
- ✅ Weekly evaluation reports
- ✅ A/B testing framework
- ✅ Automated maintenance

---

## Conclusion

The TasteBud backend has **significant implementation**, with many advanced features partially built. However, **critical bugs** prevent core functionality from working, and **organizational chaos** makes the codebase hard to maintain.

**The good news**: Most features exist, they just need:
1. Bug fixes (P0)
2. Integration (P1)
3. Organization (P2)


This will transform the codebase from "documented but broken" to "organized and working".
