# TasteBud Backend Reorganization Plan

**Purpose**: Transform chaotic 40+ flat services into organized, maintainable architecture  
**Timeline**: 1-2 weeks  
**Risk Level**: MEDIUM (requires careful import updates)

---

## Current State Analysis

### Problems with Current Structure:

```
services/ (40 files, all flat)
├── recommendation_service.py (810 lines - GOD OBJECT)
├── explanation_service.py (OLD)
├── personalized_explanation_service.py (NEW but unused)
├── mmr_service.py (exists but not integrated)
├── harmony_service.py (exists but not used)
├── similarity_matrix_service.py (exists but not precomputed)
└── ... 34 more files
```

**Issues**:
1. No logical grouping - everything mixed together
2. Unclear dependencies - circular imports likely
3. Duplicate functionality  - old vs new explanations
4. Dead code - services that exist but aren't called
5. Hard to navigate - takes 10 minutes to find relevant code

---

## Target State: Organized by Domain

```
services/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── recommendation_service.py    # Main orchestrator (slimmed down)
│   ├── retrieval_service.py         # Candidate retrieval
│   ├── reranking_service.py         # Scoring & ranking
│   └── session_service.py           # Session state management
│
├── learning/
│   ├── __init__.py
│   ├── bayesian_profile_service.py  # Phase 2: Bayesian profiles
│   ├── unified_feedback_service.py  # Central feedback processing
│   ├── online_learning_service.py   # Post-meal feedback learning
│   ├── in_session_learning_service.py # Temporary profile adjustments
│   └── weight_learning_service.py   # Dynamic weight optimization
│
├── features/
│   ├── __init__.py
│   ├── features.py                  # Feature engineering utils
│   ├── llm_features.py              # LLM-based taste profiles
│   ├── embedding_service.py         # Text → embedding
│   └── faiss_service.py             # FAISS index operations
│
├── user/
│   ├── __init__.py
│   ├── auth_service.py              # Authentication
│   ├── onboarding_service.py        # New user onboarding
│   ├── interaction_history_service.py # User interaction tracking
│   └── archetype_service.py         # Taste archetype matching
│
├── explanation/
│   ├── __init__.py
│   ├── explanation_service.py       # Current explanation generator
│   ├── personalized_explanation_service.py # Phase 4: Personalized
│   └── explanation_enhancement_service.py  # Multi-course explanations
│
├── composition/
│   ├── __init__.py
│   ├── meal_composition_service.py  # Full meal composition
│   ├── harmony_service.py           # Flavor pairing & harmony
│   └── query_service.py             # Query parsing & processing
│
├── diversity/
│   ├── __init__.py
│   ├── mmr_service.py              # Maximum Marginal Relevance
│   └── cross_encoder_service.py    # Deep semantic reranking
│
├── ml/
│   ├── __init__.py
│   ├── ml_reranking_service.py     # ML-based reranking
│   └── umap_reducer.py             # Dimensionality reduction
│
├── evaluation/
│   ├── __init__.py
│   ├── evaluation_metrics_service.py  # Metrics computation
│   ├── team_draft_interleaving_service.py # A/B testing
│   └── confidence_service.py        # Prediction confidence
│
├── infrastructure/
│   ├── __init__.py
│   ├── index_maintenance_service.py # FAISS index rebuilds
│   ├── scheduled_maintenance.py     # Background jobs
│   └── similarity_matrix_service.py # Item-item similarity matrix
│
├── context/
│   ├── __init__.py
│   ├── context_enhancement_service.py # Time/occasion context
│   └── menu_service.py              # Menu operations
│
├── communication/
│   ├── __init__.py
│   ├── email_service.py             # Email sending
│   ├── email_followup_service.py    # Post-meal emails
│   └── rating_reminder_service.py   # Rating reminders
│
└── ingestion/
    ├── __init__.py
    └── ... (existing ingestion services)
```

---

## Migration Strategy

### Phase 1: Create New Structure (Day 1)

**Steps**:
1. Create new folder structure
2. Copy files to new locations (don't delete originals yet)
3. Update imports in copied files
4. Add __init__.py files with proper exports

**Example**:
```bash
# Create folders
mkdir -p services/core
mkdir -p services/learning
mkdir -p services/features
# ... etc

# Copy files (keep originals for now)
cp services/recommendation_service.py services/core/
cp services/bayesian_profile_service.py services/learning/
# ... etc
```

**Update imports in each file**:
```python
# Old:
from services.retrieval_service import RetrievalService

# New:
from services.core.retrieval_service import RetrievalService
```

---

### Phase 2: Update All Imports (Day 2-3)

**Create import mapping**:
```python
# services/core/__init__.py
from services.core.recommendation_service import RecommendationService
from services.core.retrieval_service import RetrievalService
from services.core.reranking_service import RerankingService
from services.core.session_service import RecommendationSessionService

__all__ = [
    "RecommendationService",
    "RetrievalService",
    "RerankingService",
    "RecommendationSessionService"
]
```

**Update all consumers**:
```python
# Old:
from services.recommendation_service import RecommendationService

# New (preferred - explicit):
from services.core.recommendation_service import RecommendationService

# New (alternative - through __init__):
from services.core import RecommendationService
```

**Files to update**:
- routes/*.py (7 files)
- services/*.py (all cross-imports)
- scripts/*.py (any that import services)

---

### Phase 3: Clean Up & Remove Duplicates (Day 4)

**Merge duplicate services**:

1. **Explanation Services**:
   ```
   OLD: explanation_service.py
   NEW: personalized_explanation_service.py
   
   Strategy:
   - Keep personalized_explanation_service.py as primary
   - Add legacy mode to personalized service
   - Deprecate old explanation_service.py
   ```

2. **Filtering Logic**:
   ```
   Currently in:
   - retrieval_service.py (_apply_safety_filters)
   - recommendation_service.py (inline filtering)
   
   Strategy:
   - Create services/core/filtering_service.py
   - Consolidate all filtering logic
   - Both services call filtering_service
   ```

**Remove dead code**:
- Identify services never imported
- Move to `services/_deprecated/` folder
- Delete after confirming tests pass

---

### Phase 4: Update Tests & Documentation (Day 5)

**Update tests**:
```python
# tests/test_recommendation.py
# Old:
from services.recommendation_service import RecommendationService

# New:
from services.core.recommendation_service import RecommendationService
```

**Create README files**:

```markdown
# services/core/README.md

## Core Recommendation Services

These services form the main recommendation pipeline.

### RecommendationService
- **Purpose**: Orchestrates entire recommendation flow
- **Dependencies**: retrieval, reranking, explanation, composition
- **Called by**: routes/api.py, routes/sessions.py
- **Modified in**: Phases 1-3

### RetrievalService
- **Purpose**: Retrieves candidate items via FAISS or SQL
- **Dependencies**: faiss_service, embedding_service
- **Key methods**:
  - `retrieve_candidates()` - Profile-based retrieval
  - `retrieve_candidates_from_query()` - Query-based retrieval
- **Modified in**: Phase 3

### RerankingService
- **Purpose**: Scores and ranks candidate items
- **Dependencies**: bayesian_profile_service (optional)
- **Key methods**:
  - `rerank()` - Score items based on user profile
- **Modified in**: Phases 1-2

### RecommendationSessionService (SessionService)
- **Purpose**: Manages recommendation session state
- **Key methods**:
  - `start_session()` - Initialize new session
  - `add_excluded_item()` - Add item to exclusion list (⚠️ BUG: missing flag_modified)
  - `complete_session()` - Mark session complete
```

**Repeat for each domain folder**.

---

### Phase 5: Verification & Rollout (Day 6-7)

**Verification checklist**:
- [ ] All route handlers work
- [ ] All tests pass
- [ ] No circular imports
- [ ] All services imported correctly
- [ ] No missing dependencies

**Rollout plan**:
1. Deploy to dev environment
2. Run smoke tests
3. Monitor for import errors
4. Deploy to staging
5. Full integration testing
6. Deploy to production with rollback plan

---

## Scripts Reorganization

### Current State:
```
scripts/ (32 files, mixed purposes)
├── test_*.py (6 test files)
├── migrate_*.py (6 migration files)
├── build_*.py (3 build scripts)
└── ... 17 other scripts
```

### Target State:

```
scripts/
├── README.md              # Document all scripts
│
├── migrations/
│   ├── README.md
│   ├── migrate_taste_dimensions_7d.py
│   ├── migrate_to_bayesian_profiles.py
│   ├── migrate_add_course_cuisine.py
│   ├── migrate_add_feedback_indexes.py
│   ├── migrate_add_permanently_excluded_items.py
│   └── migrate_fix_permanently_excluded_items_type.py
│
├── data_generation/
│   ├── README.md
│   ├── generate_embeddings.py
│   ├── build_faiss_index.py
│   ├── build_similarity_matrix.py
│   ├── cluster_taste_archetypes.py
│   └── populate_features.py
│
├── maintenance/
│   ├── README.md
│   ├── regenerate_features_smart.py
│   ├── regenerate_taste_vectors_llm.py
│   ├── recompute_profiles_with_decay.py
│   └── process_rating_reminders.py
│
├── onboarding/
│   ├── README.md
│   ├── bootstrap_ratings_from_onboarding.py
│   └── bootstrap_taste_profile.py
│
├── evaluation/
│   ├── README.md
│   ├── run_offline_evaluation.py
│   ├── analyze_ab_test.py
│   ├── compute_online_metrics.py
│   └── train_reranker.py
│
├── admin/
│   ├── README.md
│   ├── reset_user.py
│   └── validate_config.py
│
└── dev/
    ├── README.md
    └── smoke_gpt_flow.py

# Move tests to proper location:
tests/
├── unit/
│   ├── test_mmr_diversity.py (moved from scripts/)
│   ├── test_course_filtering.py (moved from scripts/)
│   └── ... (new unit tests)
│
└── integration/
    ├── test_pdf_ingestion.py (moved from scripts/)
    ├── test_pdf_ingestion_detailed.py (moved from scripts/)
    ├── test_query_recommendations.py (moved from scripts/)
    └── test_recommendation_flow.py (new - end-to-end test)
```

---

## Import Path Rules

### Preferred Import Styles:

**1. Explicit Imports (BEST)**:
```python
from services.core.recommendation_service import RecommendationService
from services.learning.bayesian_profile_service import BayesianProfileService
```

**Pros**: 
- Clear where class comes from
- Easy to find definition
- No ambiguity

**2. Module-Level Imports (ACCEPTABLE)**:
```python
from services.core import RecommendationService
from services.learning import BayesianProfileService
```

**Pros**:
- Shorter
- Still clear

**Cons**:
- Requires __init__.py to export

**3. Package Imports (AVOID)**:
```python
import services.core
services.core.RecommendationService()
```

**Cons**:
- Verbose
- Awkward syntax

---

## Breaking Changes & Compatibility

### Breaking Changes:

1. **Import paths changed** - all imports need updates
2. **Some services moved to _deprecated/** - code using them will break
3. **Merged services** - some class names may change

### Backwards Compatibility Strategy:

**Option 1: Transition Period (14 days)**
Keep old imports working via shims:
```python
# services/recommendation_service.py (OLD LOCATION)
# DEPRECATED: This import path is deprecated. Use services.core.recommendation_service
import warnings
from services.core.recommendation_service import *

warnings.warn(
    "Importing from services.recommendation_service is deprecated. "
    "Use services.core.recommendation_service instead.",
    DeprecationWarning,
    stacklevel=2
)
```

**Option 2: Big Bang (Recommended)**
- Update all imports in one PR
- Test thoroughly
- Deploy atomically
- Faster, cleaner

---

## Testing Strategy

### Unit Tests Required:

```python
# tests/unit/test_imports.py
def test_core_services_import():
    from services.core import (
        RecommendationService,
        RetrievalService,
        RerankingService,
        RecommendationSessionService
    )
    assert RecommendationService is not None

def test_learning_services_import():
    from services.learning import (
        BayesianProfileService,
        UnifiedFeedbackService
    )
    assert BayesianProfileService is not None

# ... tests for each domain
```

### Integration Tests Required:

```python
# tests/integration/test_recommendation_flow.py
def test_full_recommendation_flow():
    """Test that reorganized services still work together"""
    # 1. Start session
    # 2. Get recommendations
    # 3. Provide feedback
    # 4. Get new recommendations
    # 5. Verify feedback affected results
```

---

## Rollback Plan

### If reorganization fails:

1. **Revert git commit**:
   ```bash
   git revert <commit-hash>
   git push
   ```

2. **Keep old code in place** during transition:
   ```bash
   # Don't delete old files until verified working
   mv services/recommendation_service.py services/_backup/
   ```

3. **Feature flag**:
   ```python
   USE_NEW_STRUCTURE = os.getenv("USE_NEW_SERVICE_STRUCTURE", "false") == "true"
   
   if USE_NEW_STRUCTURE:
       from services.core import RecommendationService
   else:
       from services.recommendation_service import RecommendationService
   ```

---

## Timeline & Effort Estimate

### Day 1 (4 hours): Create Structure
- Create folder hierarchy
- Copy files to new locations
- Write __init__.py files

### Day 2-3 (12 hours): Update Imports
- Update all import statements in services/
- Update all import statements in routes/
- Update all import statements in scripts/

### Day 4 (6 hours): Consolidation
- Merge duplicate services
- Remove dead code
- Create filtering_service.py

### Day 5 (4 hours): Documentation
- Write README for each domain
- Document what changed
- Update ARCHITECTURE.md

### Day 6-7 (8 hours): Testing & Rollout
- Run full test suite
- Manual smoke testing
- Deploy to dev
- Deploy to staging
- Deploy to production

**Total Effort**: ~1.5 weeks (34 hours)

---

## Success Criteria

### Before Reorganization:
- ❌ 40 files in flat services/ folder
- ❌ Hard to find relevant code
- ❌ Unclear dependencies
- ❌ Duplicate functionality

### After Reorganization:
- ✅ Organized into 10 logical domains
- ✅ Easy to find code (know which folder to look in)
- ✅ Clear dependencies (documented in READMEs)
- ✅ No duplicate services
- ✅ Tests pass
- ✅ Documentation matches reality

---

## Risks & Mitigation

### Risk 1: Breaking Production
**Probability**: HIGH if not careful  
**Impact**: CRITICAL  
**Mitigation**:
- Comprehensive test suite before deployment
- Deploy to dev/staging first
- Monitor error logs closely
- Have rollback plan ready
- Deploy during low-traffic window

### Risk 2: Circular Import Errors
**Probability**: MEDIUM  
**Impact**: HIGH  
**Mitigation**:
- Draw dependency graph before reorganization
- Ensure unidirectional dependencies
- Use lazy imports where needed
- Test import order

### Risk 3: Missing Imports
**Probability**: HIGH  
**Impact**: MEDIUM  
**Mitigation**:
- Automated tools to find all imports
- Comprehensive test coverage
- Static analysis with mypy/pylint

### Risk 4: Team Confusion
**Probability**: MEDIUM  
**Impact**: MEDIUM  
**Mitigation**:
- Document new structure clearly
- Provide onboarding guide
- Team review before merge

---

## Post-Reorganization

### Enforce Structure Going Forward:

**1. Pre-commit Hook**:
```python
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: check-service-location
      name: Check service files are in correct folders
      entry: python scripts/dev/check_service_location.py
      language: system
```

**2. Code Review Checklist**:
- [ ] New service in correct domain folder?
- [ ] __init__.py updated to export new service?
- [ ] README updated to document new service?
- [ ] Tests in correct location?

**3. Architecture Decision Records (ADRs)**:
Document major decisions:
```markdown
# ADR-001: Service Organization by Domain

## Context
Had 40+ services in flat structure, hard to navigate.

## Decision
Organize services into 10 domain folders.

## Consequences
- Easier to find code
- Clear dependencies
- More __init__.py files to maintain
```

---

## Additional Improvements

### After reorganization, consider:

1. **Dependency Injection**:
   ```python
   # Instead of:
   self.retrieval_service = RetrievalService()
   
   # Use:
   def __init__(self, retrieval_service: RetrievalService):
       self.retrieval_service = retrieval_service
   ```

2. **Interface Definitions**:
   ```python
   # services/core/interfaces.py
   from abc import ABC, abstractmethod
   
   class IRetrievalService(ABC):
       @abstractmethod
       def retrieve_candidates(self, ...):
           pass
   ```

3. **Service Registry**:
   ```python
   # services/registry.py
   class ServiceRegistry:
       _services = {}
       
       @classmethod
       def register(cls, name, service):
           cls._services[name] = service
       
       @classmethod
       def get(cls, name):
           return cls._services[name]
   ```

But these are **future improvements** - focus on reorganization first.

---

## Conclusion

This reorganization will transform the codebase from:
- **Chaotic**: 40 files, hard to navigate
- **Unclear**: What does each service do?
- **Duplicated**: Multiple ways to do same thing

To:
- **Organized**: 10 clear domains
- **Documented**: README in each folder
- **Maintainable**: Easy to find and modify code

**Estimated improvement**:
- 70% faster to find relevant code
- 50% fewer import errors
- 80% easier onboarding for new developers

**When to start**: After P0 bugs are fixed (so we have working baseline to reorganize from)
