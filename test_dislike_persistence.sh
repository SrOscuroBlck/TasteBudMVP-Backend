#!/bin/bash

# Test Dislike Persistence - Reproduces user's exact scenario
# Scenario 1: Dislike items in full meal composition → Start new session → Check if they reappear
# Scenario 2: Skip single item → Get more recs → Check if it reappears

set -e  # Exit on error

TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzODViNzBlNC0zNWY2LTRkOGUtOTExMy1kMWVmMTY3MmFmZWMiLCJ0eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzcxMTAyMjQ0fQ._iyGM4kwblXOAjkuhrxXiKotHGCnXm7BIM4conidMqg"
RESTAURANT_ID="b62a20c0-3742-4083-b8f7-ebaf91bf0b12"  # Crepes & Waffles
API_URL="http://localhost:8010/api/v1"

echo "========================================="
echo "DISLIKE PERSISTENCE TEST"
echo "Reproducing User's Exact Scenario"
echo "========================================="
echo

# Helper function to extract JSON field
get_json_field() {
  echo "$1" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data$2)" 2>/dev/null || echo ""
}

echo "════════════════════════════════════════"
echo "SCENARIO 1: Full Meal Composition Rejection"
echo "════════════════════════════════════════"
echo

echo "STEP 1: Start Full Meal Session"
echo "--------------------------------------"
SESSION_1=$(curl -s -X POST "$API_URL/sessions/start" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"restaurant_id\": \"$RESTAURANT_ID\",
    \"meal_intent\": \"full_meal\",
    \"budget\": 100.0
  }")

echo "$SESSION_1" | python3 -m json.tool
SESSION_1_ID=$(echo "$SESSION_1" | python3 -c "import sys, json; print(json.load(sys.stdin).get('session_id', ''))" 2>/dev/null)

echo "✓ Session created: $SESSION_1_ID"
echo

if [ -z "$SESSION_1_ID" ]; then
  echo "❌ ERROR: Didn't get session_id. Exiting."
  exit 1
fi

echo "Getting initial recommendations..."
INITIAL_RECS=$(curl -s -X POST "$API_URL/sessions/$SESSION_1_ID/next" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"count\": 10}")

echo "$INITIAL_RECS" | python3 -m json.tool
echo

# Extract composition items (first composition from items array)
COMPOSITION_1_ID=$(echo "$INITIAL_RECS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('items', [{}])[0].get('composition_id', ''))" 2>/dev/null)
APPETIZER_1=$(echo "$INITIAL_RECS" | python3 -c "import sys, json; data=json.load(sys.stdin); items=data.get('items', [{}])[0].get('items', []); print(next((i['item_id'] for i in items if i.get('course')=='appetizer'), ''))" 2>/dev/null)
MAIN_1=$(echo "$INITIAL_RECS" | python3 -c "import sys, json; data=json.load(sys.stdin); items=data.get('items', [{}])[0].get('items', []); print(next((i['item_id'] for i in items if i.get('course')=='main'), ''))" 2>/dev/null)
DESSERT_1=$(echo "$INITIAL_RECS" | python3 -c "import sys, json; data=json.load(sys.stdin); items=data.get('items', [{}])[0].get('items', []); print(next((i['item_id'] for i in items if i.get('course')=='dessert'), ''))" 2>/dev/null)

APPETIZER_1_NAME=$(echo "$INITIAL_RECS" | python3 -c "import sys, json; data=json.load(sys.stdin); items=data.get('items', [{}])[0].get('items', []); print(next((i['name'] for i in items if i.get('course')=='appetizer'), ''))" 2>/dev/null)
MAIN_1_NAME=$(echo "$INITIAL_RECS" | python3 -c "import sys, json; data=json.load(sys.stdin); items=data.get('items', [{}])[0].get('items', []); print(next((i['name'] for i in items if i.get('course')=='main'), ''))" 2>/dev/null)
DESSERT_1_NAME=$(echo "$INITIAL_RECS" | python3 -c "import sys, json; data=json.load(sys.stdin); items=data.get('items', [{}])[0].get('items', []); print(next((i['name'] for i in items if i.get('course')=='dessert'), ''))" 2>/dev/null)

echo "✓ Got composition (ID: $COMPOSITION_1_ID):"
echo "  Appetizer: $APPETIZER_1_NAME ($APPETIZER_1)"
echo "  Main: $MAIN_1_NAME ($MAIN_1)"
echo "  Dessert: $DESSERT_1_NAME ($DESSERT_1)"
echo

if [ -z "$APPETIZER_1" ] || [ -z "$MAIN_1" ] || [ -z "$COMPOSITION_1_ID" ]; then
  echo "❌ ERROR: Didn't get full composition. Exiting."
  exit 1
fi

echo "STEP 2: USER DISLIKES APPETIZER AND MAIN (clicks X buttons)"
echo "--------------------------------------"
echo "Submitting composition feedback with rejected items..."

COMP_FEEDBACK=$(curl -s -X POST "$API_URL/sessions/$SESSION_1_ID/composition/feedback" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"composition_id\": \"$COMPOSITION_1_ID\",
    \"appetizer_feedback\": \"skip\",
    \"main_feedback\": \"skip\",
    \"dessert_feedback\": \"accepted\",
    \"composition_action\": \"regenerate_partial\"
  }")

echo "$COMP_FEEDBACK" | python3 -m json.tool
echo "✓ Rejected: $APPETIZER_1_NAME and $MAIN_1_NAME"
echo

echo "STEP 3: Click 'Update Meal' - Get new composition"
echo "--------------------------------------"
NEXT_RECS=$(curl -s -X POST "$API_URL/sessions/$SESSION_1_ID/next" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"count\": 10}")

echo "$NEXT_RECS" | python3 -m json.tool
echo

echo "STEP 4: Complete session (simulate ordering)"
echo "--------------------------------------"
curl -s -X POST "$API_URL/sessions/$SESSION_1_ID/complete" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"selected_items\": [\"$DESSERT_1\"]}" | python3 -m json.tool
echo

echo "⏰ Waiting 2 seconds (simulate time passing)..."
sleep 2
echo

echo "STEP 5: 🔍 CRITICAL TEST - Start NEW session"
echo "--------------------------------------"
echo "This should NOT show the rejected items!"
echo

SESSION_2=$(curl -s -X POST "$API_URL/sessions/start" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"restaurant_id\": \"$RESTAURANT_ID\",
    \"meal_intent\": \"full_meal\",
    \"budget\": 100.0
  }")

SESSION_2_ID=$(echo "$SESSION_2" | python3 -c "import sys, json; print(json.load(sys.stdin).get('session_id', ''))" 2>/dev/null)

if [ -z "$SESSION_2_ID" ]; then
  echo "❌ ERROR: Didn't get session_id for second session. Exiting."
  exit 1
fi

echo "✓ New session created: $SESSION_2_ID"
echo

echo "Getting recommendations for NEW session..."
NEW_SESSION_RECS=$(curl -s -X POST "$API_URL/sessions/$SESSION_2_ID/next" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"count\": 10}")

echo "$NEW_SESSION_RECS" | python3 -m json.tool

APPETIZER_2=$(echo "$NEW_SESSION_RECS" | python3 -c "import sys, json; data=json.load(sys.stdin); items=data.get('items', [{}])[0].get('items', []); print(next((i['item_id'] for i in items if i.get('course')=='appetizer'), ''))" 2>/dev/null)
MAIN_2=$(echo "$NEW_SESSION_RECS" | python3 -c "import sys, json; data=json.load(sys.stdin); items=data.get('items', [{}])[0].get('items', []); print(next((i['item_id'] for i in items if i.get('course')=='main'), ''))" 2>/dev/null)

APPETIZER_2_NAME=$(echo "$NEW_SESSION_RECS" | python3 -c "import sys, json; data=json.load(sys.stdin); items=data.get('items', [{}])[0].get('items', []); print(next((i['name'] for i in items if i.get('course')=='appetizer'), ''))" 2>/dev/null)
MAIN_2_NAME=$(echo "$NEW_SESSION_RECS" | python3 -c "import sys, json; data=json.load(sys.stdin); items=data.get('items', [{}])[0].get('items', []); print(next((i['name'] for i in items if i.get('course')=='main'), ''))" 2>/dev/null)

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 SCENARIO 1 RESULTS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Previously REJECTED:"
echo "  ❌ Appetizer: $APPETIZER_1_NAME ($APPETIZER_1)"
echo "  ❌ Main: $MAIN_1_NAME ($MAIN_1)"
echo
echo "New session shows:"
echo "  Appetizer: $APPETIZER_2_NAME ($APPETIZER_2)"
echo "  Main: $MAIN_2_NAME ($MAIN_2)"
echo

# Check if rejected items reappeared
APPETIZER_REAPPEARED="NO"
MAIN_REAPPEARED="NO"

if [ "$APPETIZER_1" = "$APPETIZER_2" ]; then
  APPETIZER_REAPPEARED="YES ⚠️ BUG!"
fi

if [ "$MAIN_1" = "$MAIN_2" ]; then
  MAIN_REAPPEARED="YES ⚠️ BUG!"
fi

echo "Appetizer reappeared? $APPETIZER_REAPPEARED"
echo "Main reappeared? $MAIN_REAPPEARED"
echo

if [ "$APPETIZER_REAPPEARED" = "YES ⚠️ BUG!" ] || [ "$MAIN_REAPPEARED" = "YES ⚠️ BUG!" ]; then
  echo "❌ FAILED: Rejected items appeared again!"
  echo "   This is the bug the user reported."
else
  echo "✅ PASSED: Rejected items did NOT reappear"
fi
echo

echo
echo "════════════════════════════════════════"
echo "SCENARIO 2: Single Item Skip"
echo "════════════════════════════════════════"
echo

echo "STEP 1: Start Main Course Session"
echo "--------------------------------------"
SESSION_3=$(curl -s -X POST "$API_URL/sessions/start" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d"{
    \"restaurant_id\": \"$RESTAURANT_ID\",
    \"meal_intent\": \"main_only\",
    \"budget\": 50.0
  }")

echo "$SESSION_3" | python3 -m json.tool
SESSION_3_ID=$(echo "$SESSION_3" | python3 -c "import sys, json; print(json.load(sys.stdin).get('session_id', ''))" 2>/dev/null)

if [ -z "$SESSION_3_ID" ]; then
  echo "❌ ERROR: Didn't get session_id. Exiting."
  exit 1
fi

echo "✓ Session created: $SESSION_3_ID"
echo

echo "Getting initial recommendations..."
INITIAL_SINGLE=$(curl -s -X POST "$API_URL/sessions/$SESSION_3_ID/next" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"count\": 10}")

echo "$INITIAL_SINGLE" | python3 -m json.tool
echo

FIRST_ITEM=$(echo "$INITIAL_SINGLE" | python3 -c "import sys, json; items=json.load(sys.stdin).get('items', []); print(items[0]['item_id'] if items else '')" 2>/dev/null)
FIRST_ITEM_NAME=$(echo "$INITIAL_SINGLE" | python3 -c "import sys, json; items=json.load(sys.stdin).get('items', []); print(items[0]['name'] if items else '')" 2>/dev/null)

echo "✓ First recommendation: $FIRST_ITEM_NAME ($FIRST_ITEM)"
echo

if [ -z "$FIRST_ITEM" ]; then
  echo "❌ ERROR: Didn't get any recommendations. Exiting."
  exit 1
fi

echo "STEP 2: USER CLICKS SKIP BUTTON"
echo "--------------------------------------"
SKIP_FEEDBACK=$(curl -s -X POST "$API_URL/sessions/$SESSION_3_ID/feedback" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"item_id\": \"$FIRST_ITEM\",
    \"feedback_type\": \"skip\",
    \"comment\": \"Don't want this\"
  }")

echo "$SKIP_FEEDBACK" | python3 -m json.tool
echo "✓ Skipped: $FIRST_ITEM_NAME"
echo

echo "STEP 3: Get next recommendation"
echo "--------------------------------------"
NEXT_REC=$(curl -s -X POST "$API_URL/sessions/$SESSION_3_ID/next" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"count\": 10}")

echo "$NEXT_REC" | python3 -m json.tool
echo

echo "STEP 4: Get another batch of recommendations"
echo "--------------------------------------"
ANOTHER_BATCH=$(curl -s -X POST "$API_URL/sessions/$SESSION_3_ID/next" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"count\": 10}")

echo "$ANOTHER_BATCH" | python3 -m json.tool
echo

# Check if skipped item appears in either batch
SKIPPED_IN_NEXT=$(echo "$NEXT_REC" | python3 -c "import sys, json; recs=json.load(sys.stdin).get('items', []); print('YES' if any(r['item_id'] == '$FIRST_ITEM' for r in recs) else 'NO')" 2>/dev/null)
SKIPPED_IN_ANOTHER=$(echo "$ANOTHER_BATCH" | python3 -c "import sys, json; recs=json.load(sys.stdin).get('items', []); print('YES' if any(r['item_id'] == '$FIRST_ITEM' for r in recs) else 'NO')" 2>/dev/null)

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 SCENARIO 2 RESULTS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Skipped item: $FIRST_ITEM_NAME ($FIRST_ITEM)"
echo
echo "Appeared in next batch? $SKIPPED_IN_NEXT"
echo "Appeared in another batch? $SKIPPED_IN_ANOTHER"
echo

if [ "$SKIPPED_IN_NEXT" = "YES" ] || [ "$SKIPPED_IN_ANOTHER" = "YES" ]; then
  echo "❌ FAILED: Skipped item appeared again within same session!"
  echo "   This is the bug the user reported."
else
  echo "✅ PASSED: Skipped item did NOT reappear in same session"
fi
echo

echo
echo "========================================="
echo "📋 FINAL SUMMARY"
echo "========================================="
echo
echo "Scenario 1 (Full Meal):"
if [ "$APPETIZER_REAPPEARED" = "YES ⚠️ BUG!" ] || [ "$MAIN_REAPPEARED" = "YES ⚠️ BUG!" ]; then
  echo "  ❌ FAILED - Rejected items reappeared in new session"
else
  echo "  ✅ PASSED - Rejected items did not reappear"
fi
echo
echo "Scenario 2 (Single Skip):"
if [ "$SKIPPED_IN_NEXT" = "YES" ] || [ "$SKIPPED_IN_ANOTHER" = "YES" ]; then
  echo "  ❌ FAILED - Skipped item reappeared in same session"
else
  echo "  ✅ PASSED - Skipped item did not reappear"
fi
echo
echo "========================================="
echo

# Check user's interaction history for the items
echo "🔍 DEBUG: Checking interaction history..."
echo "--------------------------------------"
curl -s -X GET "$API_URL/users/385b70e4-35f6-4d8e-9113-d1ef1672afec/interaction-history?item_id=$FIRST_ITEM" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool || echo "No interaction history endpoint"
echo

echo "🔍 DEBUG: Checking user profile for ingredient_penalties..."
echo "--------------------------------------"
USER_PROFILE=$(curl -s -X GET "$API_URL/users/385b70e4-35f6-4d8e-9113-d1ef1672afec/profile" \
  -H "Authorization: Bearer $TOKEN")
echo "$USER_PROFILE" | python3 -c "import sys, json; data=json.load(sys.stdin); print('ingredient_penalties:', data.get('ingredient_penalties', 'NOT FOUND'))" 2>/dev/null || echo "Could not check"
echo

echo "✅ Test complete. Check results above."
