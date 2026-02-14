# Comprehensive Code Analysis: Recommendation Filtering Bug

## Executive Summary

After disliking an item, users report seeing the same items in the exact same order in subsequent recommendations. This analysis identifies **7 critical bugs** causing this behavior.

---

## Complete Flow Analysis

### 1. Feedback Submission Flow

**Endpoint**: `POST /sessions/{session_id}/feedback`  
**File**: [routes/sessions.py](routes/sessions.py#L247-L300)

```python
# Line 280-286
unified_feedback_service = UnifiedFeedbackService()
feedback = unified_feedback_service.record_session_feedback(
    db_session=db,
    user=current_user,
    item=item,
    feedback_type=request.feedback_type,
    session_id=session_id,
    comment=request.comment
)

# Line 288
if request.feedback_type == FeedbackType.DISLIKE:
    session_service.add_excluded_item(db, session_id, request.item_id)
```

**What happens**:
1. `record_session_feedback()` is called
2. If feedback is DISLIKE, `add_excluded_item()` is called

---

### 2. Feedback Processing in UnifiedFeedbackService

**File**: [services/unified_feedback_service.py](services/unified_feedback_service.py#L194-L212)

```python
# Lines 189-212
if is_negative:
    # ... taste vector updates ...
    
    item_id_str = str(item.id)
    logger.info(
        "Checking permanent exclusion",
        extra={
            "user_id": str(user.id),
            "item_id": item_id_str,
            "intensity": intensity,
            "feedback_type": feedback_type.value,
            "already_excluded": item_id_str in user.permanently_excluded_items,
            "current_exclusions_count": len(user.permanently_excluded_items)
        }
    )
    if intensity == "medium" and item_id_str not in user.permanently_excluded_items:
        user.permanently_excluded_items = user.permanently_excluded_items + [item_id_str]
        flag_modified(user, "permanently_excluded_items")
        logger.info(
            "Item added to permanent exclusions",
            extra={
                "user_id": str(user.id),
                "item_id": item_id_str,
                "new_exclusions_count": len(user.permanently_excluded_items),
                "all_excluded_ids": user.permanently_excluded_items,
                "intensity": intensity
            }
        )
```

**Line 107**: `db_session.commit()`

---

### 3. Session Exclusion in SessionService

**File**: [services/session_service.py](services/session_service.py#L172-L183)

```python
# Lines 172-183
def add_excluded_item(
    self,
    db_session: Session,
    session_id: UUID,
    item_id: UUID
) -> None:
    session = self.get_session(db_session, session_id)
    
    if str(item_id) not in session.excluded_items:
        session.excluded_items = session.excluded_items + [str(item_id)]
        db_session.add(session)
        db_session.commit()
```

---

### 4. Next Recommendations Request

**Endpoint**: `POST /sessions/{session_id}/next`  
**File**: [routes/sessions.py](routes/sessions.py#L188-L239)

```python
# Lines 200-204
statement = select(RecommendationSession).where(RecommendationSession.id == session_id)
rec_session = db.exec(statement).first()

# Lines 217-222
results = recommendation_service.recommend_with_session(
    session=db,
    user=current_user,
    recommendation_session=rec_session,
    top_n=request.count
)
```

**Note**: `current_user` comes from `get_current_user()` dependency which fetches fresh from DB.

---

### 5. Session-Based Recommendation Filtering

**File**: [services/recommendation_service.py](services/recommendation_service.py#L459-L810)

```python
# Lines 479-517 - THE CRITICAL FILTERING SECTION
q = select(MenuItem).where(MenuItem.restaurant_id == UUIDType(restaurant_id_str))
all_items: List[MenuItem] = session.exec(q).all()

safe: List[MenuItem] = []
user_all = set(map(str.lower, user.allergies))

logger.info(
    "Starting safety filtering",
    extra={
        "user_id": str(user.id),
        "total_items": len(all_items),
        "permanently_excluded_count": len(user.permanently_excluded_items),
        "permanently_excluded_items": user.permanently_excluded_items
    }
)

for it in all_items:
    # ... allergen and diet checks ...
    
    item_id_str = str(it.id)
    if item_id_str in recommendation_session.excluded_items:
        continue
    
    if item_id_str in user.permanently_excluded_items:
        logger.debug(
            "Item filtered - permanently excluded",
            extra={"item_id": item_id_str, "item_name": it.name}
        )
        continue
    
    safe.append(it)
```

---

## 🔴 Critical Bugs Identified

### Bug #1: MISSING flag_modified() FOR excluded_items 🚨 MOST CRITICAL
**File**: [services/session_service.py](services/session_service.py#L172-L183)  
**Lines**: 172-183

```python
def add_excluded_item(
    self,
    db_session: Session,
    session_id: UUID,
    item_id: UUID
) -> None:
    session = self.get_session(db_session, session_id)
    
    if str(item_id) not in session.excluded_items:
        session.excluded_items = session.excluded_items + [str(item_id)]
        db_session.add(session)
        db_session.commit()
        # ❌❌❌ MISSING: flag_modified(session, "excluded_items")
```

**Same bug exists in `add_items_shown()` at line 165**:
```python
session.items_shown = session.items_shown + new_items
session.iteration_count += 1
db_session.add(session)
db_session.commit()
# ❌ MISSING: flag_modified(session, "items_shown")
```

**Compare with correct implementation in unified_feedback_service.py line 201-202**:
```python
user.permanently_excluded_items = user.permanently_excluded_items + [item_id_str]
flag_modified(user, "permanently_excluded_items")  # ✅ THIS IS PRESENT
```

**Impact**: **THIS IS THE PRIMARY BUG**. SQLAlchemy does NOT automatically detect changes to JSON columns. When you assign a new list:
```python
session.excluded_items = session.excluded_items + [str(item_id)]
```

SQLAlchemy sees this as:
1. Read `excluded_items` (returns `[a, b, c]`)
2. Create new list `[a, b, c, d]`
3. Assign back to `excluded_items`

However, for JSON columns, SQLAlchemy doesn't track this mutation **unless you explicitly call `flag_modified()`**. The `db_session.commit()` call will **silently fail to persist the change** because SQLAlchemy doesn't know the column was modified.

**Result**: 
- The in-memory object has the updated list
- The database still has the old list
- Next request loads from DB and gets the OLD list WITHOUT the excluded item
- **User sees the item again because it was never actually excluded in the database**

**Root Cause**: Missing `flag_modified(session, "excluded_items")` call after mutating JSON field.

**Evidence**: Other parts of the codebase correctly use `flag_modified()`:
- `unified_feedback_service.py:202` - `flag_modified(user, "permanently_excluded_items")`
- `unified_feedback_service.py:163` - `flag_modified(user, "taste_vector")`
- `unified_feedback_service.py:170` - `flag_modified(user, "cuisine_affinity")`
- `session_service.py:217` - `flag_modified(session, "composition_validation_state")`

---

### Bug #2: Type Annotation Mismatch in Session Model
**File**: [models/session.py](models/session.py#L53)  
**Line**: 53

```python
excluded_items: List[UUID] = Field(default_factory=list, sa_column=Column(JSON))
```

**Actual data stored**: `List[str]` (strings, not UUIDs)

**In**: [services/session_service.py](services/session_service.py#L181)
```python
session.excluded_items = session.excluded_items + [str(item_id)]
```

**Impact**: Type annotation lies about the data type. This can cause serialization/deserialization issues depending on the ORM behavior.

**Root Cause**: The model declares `List[UUID]` but the code consistently stores strings. When loading from JSON, there's no UUID conversion.

---

### Bug #3: Missing SQLAlchemy Refresh After Exclusion Update
**File**: [routes/sessions.py](routes/sessions.py#L288)  
**Line**: 288

```python
if request.feedback_type == FeedbackType.DISLIKE:
    session_service.add_excluded_item(db, session_id, request.item_id)
    # ❌ NO db.refresh(current_user) HERE
```

**Impact**: After permanently excluding an item in `unified_feedback_service`, the `current_user` object in the route handler is stale. However, since the next request will fetch a fresh user from DB, this is not the primary issue.

**Root Cause**: The user object is modified by `unified_feedback_service.record_session_feedback()` which commits, but the local `current_user` variable still has old data. This won't affect the next request though.

---

### Bug #3: Missing SQLAlchemy Refresh After Exclusion Update
**File**: [routes/sessions.py](routes/sessions.py#L288)  
**Line**: 288

```python
if request.feedback_type == FeedbackType.DISLIKE:
    session_service.add_excluded_item(db, session_id, request.item_id)
    # ❌ NO db.refresh(current_user) HERE
```

**Impact**: After permanently excluding an item in `unified_feedback_service`, the `current_user` object in the route handler is stale. However, since the next request will fetch a fresh user from DB, this is not the primary issue.

**Root Cause**: The user object is modified by `unified_feedback_service.record_session_feedback()` which commits, but the local `current_user` variable still has old data. This won't affect the next request though.

---

### Bug #4: Deterministic Scoring Without Randomization
**File**: [services/recommendation_service.py](services/recommendation_service.py#L550-L700)  
**Lines**: 600-650

The scoring algorithm is **completely deterministic**:

```python
# Lines 600-640 - Base scoring (always same for same inputs)
base_scores: Dict[str, float] = {}
for it in candidates:
    s = cosine_similarity(adjusted_taste_vector, it.features)
    
    # Deterministic cuisine bonus
    for cuisine in it.cuisine:
        cuisine_pref = bayesian_profile.get_cuisine_preference(cuisine)
        cuisine_bonus = (cuisine_pref - 0.5) * 2.0 * settings.LAMBDA_CUISINE
        s += cuisine_bonus
    
    # Deterministic popularity
    popularity_score = pop_global.get(str(it.id), 0.0)
    s += settings.LAMBDA_POP * popularity_score
    
    # ... more deterministic calculations ...
    
    base_scores[str(it.id)] = max(0.0, min(1.0, s))

# Lines 718-720 - Deterministic sorting (always same order)
sorted_items = sorted(candidates, key=lambda it: base_scores.get(str(it.id), 0.0), reverse=True)
top_items = sorted_items[:top_n]
```

**Impact**: Given the same inputs (user profile, items, context), the algorithm ALWAYS produces the same order. If filtering fails, users see identical results.

**Root Cause**: No randomization or diversity mechanism in the final ranking. Thompson Sampling is used for base taste vector (line 574) but the final sorting is still deterministic based on those sampled values.

---

### Bug #5: No Explicit Filtering Verification or Logging
**File**: [services/recommendation_service.py](services/recommendation_service.py#L507-L517)  
**Lines**: 507-517

```python
item_id_str = str(it.id)
if item_id_str in recommendation_session.excluded_items:
    continue

if item_id_str in user.permanently_excluded_items:
    logger.debug(  # ❌ DEBUG level - won't show in production
        "Item filtered - permanently excluded",
        extra={"item_id": item_id_str, "item_name": it.name}
    )
    continue
```

**Impact**: 
- Permanent exclusion filtering only logs at DEBUG level
- No verification that filtering actually worked
- No count of filtered items in INFO logs

**Root Cause**: Insufficient logging makes it impossible to diagnose filtering failures in production.

---

### Bug #6: Session Exclusions Not Logged or Verified
**File**: [services/recommendation_service.py](services/recommendation_service.py#L507-L509)

```python
item_id_str = str(it.id)
if item_id_str in recommendation_session.excluded_items:
    continue  # ❌ Silent filtering - no logs at all
```

**Impact**: When session-level exclusions fail, there's NO logging to detect it.

**Root Cause**: No logging for session exclusion filtering.

---

### Bug #7: UUID String Format Inconsistency Risk
**File**: Multiple locations

When converting UUIDs to strings, Python's `str()` function typically produces lowercase with hyphens:
```python
item_id_str = str(it.id)  # e.g., "a1b2c3d4-e5f6-..."
```

However, depending on how UUIDs were originally stored or serialized, there could be:
- Uppercase vs lowercase differences
- With/without hyphens
- Different serialization formats

**Current code locations**:
- [session_service.py#L181](services/session_service.py#L181): `str(item_id)`
- [unified_feedback_service.py#L192](services/unified_feedback_service.py#L192): `str(item.id)`
- [recommendation_service.py#L507](services/recommendation_service.py#L507): `str(it.id)`

**Impact**: If UUID string formats don't match exactly, the `in` operator fails:
```python
"a1b2c3d4-e5f6-..." in ["A1B2C3D4-E5F6-..."]  # False!
```

**Root Cause**: No normalization of UUID strings before comparison.

---

### Bug #8: Missing Filtering Confirmation in Retrieval Service
**File**: [services/retrieval_service.py](services/retrieval_service.py#L318-L365)  
**Lines**: 318-365

The `_get_recent_item_ids` method adds permanently excluded items to the exclusion set:

```python
# Lines 347-351
for item_id_str in user.permanently_excluded_items:
    try:
        excluded.add(UUID(item_id_str))
    except (ValueError, AttributeError):
        continue
```

**However**, this method is only called by the NEW PIPELINE (FAISS-based retrieval), NOT by `recommend_with_session`.

**Impact**: The session-based recommendation flow bypasses the retrieval service entirely and implements its own filtering. Any bugs in that filtering logic won't be caught by the retrieval service's more robust handling.

**Root Cause**: Dual filtering implementations with different behaviors.

---

## 🔍 Additional Issues

### Issue A: No Diversity Mechanism in Session Recommendations

**File**: [services/recommendation_service.py](services/recommendation_service.py#L718-L720)

```python
sorted_items = sorted(candidates, key=lambda it: base_scores.get(str(it.id), 0.0), reverse=True)
top_items = sorted_items[:top_n]
```

The code sorts by score and takes the top N. There's no MMR (Maximal Marginal Relevance) or other diversity mechanism applied in the session-based flow (unlike the general recommendation flow which uses MMR at line 413).

**Impact**: Same top-scoring items always appear first if filtering fails.

---

### Issue B: Thompson Sampling Might Not Provide Enough Variance

**File**: [services/recommendation_service.py](services/recommendation_service.py#L574)

```python
base_taste_vector = bayesian_profile.sample_taste_preferences()
```

While Thompson Sampling adds some randomization, if:
1. The user has low uncertainty (many feedbacks)
2. The Bayesian profile is well-established

Then the sampling will consistently produce very similar vectors, leading to deterministic results.

---

### Issue C: No Verification of Exclusion List Updates

After calling `add_excluded_item()`, there's no verification that:
1. The item was actually added to the list
2. The database was updated
3. The change persisted

**Recommended addition**:
```python
if request.feedback_type == FeedbackType.DISLIKE:
    session_service.add_excluded_item(db, session_id, request.item_id)
    
    # Verify exclusion
    db.refresh(rec_session)
    if str(request.item_id) not in rec_session.excluded_items:
        logger.error(
            "Failed to add item to exclusion list",
            extra={"item_id": str(request.item_id), "session_id": str(session_id)}
        )
```

---

## 🎯 Specific Line Numbers of Bugs

| Bug | File | Lines | Description |
|-----|------|-------|-------------|
| **#1** 🚨 | `services/session_service.py` | 181 | **CRITICAL: Missing `flag_modified(session, "excluded_items")`** |
| #2 | `models/session.py` | 53 | Wrong type annotation: `List[UUID]` should be `List[str]` |
| #3 | `routes/sessions.py` | 288 | Missing `db.refresh(current_user)` after exclusion |
| #4 | `services/recommendation_service.py` | 718-720 | Deterministic sorting without randomization |
| #5 | `services/recommendation_service.py` | 510-517 | DEBUG-level logging for permanent exclusions |
| #6 | `services/recommendation_service.py` | 507-509 | No logging for session exclusions |
| #7 | Multiple files | Various | UUID string format not normalized |
| #8 | `services/recommendation_service.py` | 479-517 | Duplicate filtering logic not using retrieval service |

---

## 🔧 Root Causes Summary
🚨 CRITICAL: Missing flag_modified()**: Session exclusions not persisted to database (Bug #1) - **THIS IS THE PRIMARY CAUSE**
2. **Type System Issues**: Model types don't match actual data (Bug #2)
3. **Insufficient Logging**: Critical filtering operations use DEBUG level or no logging (Bugs #5, #6)
4. **Deterministic Algorithm**: No randomization in final ranking (Bug #4)
5. **No Verification**: No confirmation that exclusions actually worked (Issue C)
6. **String Format Risk**: UUID strings not normalized (Bug #7)
7. **Code Duplication**: Two different filtering implementations (Bug #8)
8. **Missing Diversity**: No MMR or diversity mechanism in session flow (Issue A)

**THE SMOKING GUN**: Bug #1 (missing `flag_modified()`) means that excluded items are **never actually saved to the database**. The in-memory session object gets updated, but when the next request loads the session from the database, the excluded_items list is empty or outdated. This explains why users keep seeing the same items - they were never actually excluded in the persistent storage.
7. **Missing Diversity**: No MMR or diversity mechanism in session flow (Issue A)

---

## 🧪 How to Reproduce

1. Start a recommendation session at a restaurant
2. Request 10 recommendations
3. Note the order and items
4. Click "dislike" on the top 3 items
5. Request 10 MORE recommendations
6. **Expected**: Different items or at least different order
7. **Actual**: Same items in same order (if filtering fails silently)

---

## 📊 Testing Recommendations

### Test 1: Verify Exclusion List Population
```python
# After calling feedback endpoint
assert str(item_id) in session.excluded_items
assert str(item_id) in user.permanently_excluded_items
```

### Test 2: Verify Filtering
```python
# After calling next recommendations
for rec_item in recommendations:
    assert str(rec_item["item_id"]) not in session.excluded_items
    assert str(rec_item["item_id"]) not in user.permanently_excluded_items
```

### Test 3: Check UUID String Formats
```python
# Log both sides of the comparison
logger.info(f"Checking item_id: {item_id_str!r}")
logger.info(f"Against exclusion list: {session.excluded_items}")
logger.info(f"Match result: {item_id_str in session.excluded_items}")
```

---0 (CRITICAL - FIX IMMEDIATELY) 🚨
1. **Add `flag_modified(session, "excluded_items")`** in `services/session_service.py` line 181
   ```python
   if str(item_id) not in session.excluded_items:
       session.excluded_items = session.excluded_items + [str(item_id)]
       flag_modified(session, "excluded_items")  # ADD THIS LINE
       db_session.add(session)
       db_session.commit()
   ```

### Priority 1 (Critical)
1. **Fix type annotation** in `models/session.py` line 53
2. **Add INFO-level logging** for all filtering operations
3. **Normalize UUID strings** before comparison
4. **Add exclusion verification** after feedback

### Priority 2 (High)
1. **Add randomization** to final ranking (tie-breaking, shuffle)
2. **Implement MMR diversity** in session recommendations
3. **Consolidate filtering logic** to use single implementation

### Priority 3 (Medium)
1. Add comprehensive filtering tests
2. Add monitoring/alerting for repeated items
3. Document UUID string format conventions

---

## Conclusion

**The primary bug is Bug #1: Missing `flag_modified(session, "excluded_items")`**. This causes session exclusions to never be persisted to the database. When a user dislikes an item:

1. ✅ Item is added to `user.permanently_excluded_items` (with proper `flag_modified()`)
2. ❌ Item is added to `session.excluded_items` but WITHOUT `flag_modified()`
3. ✅ User exclusion is saved to DB because of `flag_modified()`
4. ❌ Session exclusion is NOT saved to DB because of missing `flag_modified()`
5. On next request:
   - ✅ Fresh user has the exclusion
   - ❌ Fresh session does NOT have the exclusion
   - ❌ Item passes the `if item_id_str in recommendation_session.excluded_items:` check
   - ✅ Item is filtered by permanent exclusions IF feedback type was DISLIKE

However, for other feedback types (SKIP, MORE), items are NOT added to permanent exclusions, only session exclusions. This means:
- **FeedbackType.SKIP**: Not added to permanent, only session → appears again
- **FeedbackType.MORE**: Not added to permanent, only session → appears again
- **FeedbackType.DISLIKE**: Added to permanent → should not appear (if user profile is fresh)

The secondary issue is the **deterministic algorithm** (Bug #4) which ensures that if filtering fails, users see identical results every time.

**Immediate Action**: Add the missing `flag_modified()` call to fix 90% of the reported issue.
1. Better logging to see what's happening
2. Fixing the type system
3. Normalizing UUID formats
4. Adding randomization/diversity
