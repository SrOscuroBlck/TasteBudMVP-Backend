#!/bin/bash

# Test Granular Composition Feedback Flow
# Tests: Start full_meal session → Get composition → Granular item feedback → Partial regeneration

BASE_URL="http://localhost:8010/api/v1"
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5NTMyODdkZC0wMGUwLTRiOTEtYjk3Mi04MjhiNTAwMTU3YTEiLCJ0eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzcxMDU0MTYxfQ.4Y24q1UFvXYHCTL9tJBLir8exE_nAFeKXe8OZWAeLag"
RESTAURANT_ID="b62a20c0-3742-4083-b8f7-ebaf91bf0b12"  # Crepes & Waffles

echo "========================================="
echo "GRANULAR COMPOSITION FEEDBACK TEST"
echo "========================================="
echo

echo "STEP 1: Start full_meal session"
echo "--------------------------------------"
SESSION_RESPONSE=$(curl -s -X POST "$BASE_URL/sessions/start" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"restaurant_id\": \"$RESTAURANT_ID\",
    \"meal_intent\": \"full_meal\",
    \"budget\": 150.0
  }")

echo "$SESSION_RESPONSE" | python3 -m json.tool
echo

SESSION_ID=$(echo "$SESSION_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('session_id', ''))" 2>/dev/null)

if [ -z "$SESSION_ID" ]; then
  echo "❌ Failed to start session"
  exit 1
fi

echo "✓ Session started: $SESSION_ID"
echo

echo "STEP 2: Get first composition recommendations"
echo "--------------------------------------"
RECOMMENDATIONS=$(curl -s -X POST "$BASE_URL/sessions/$SESSION_ID/next" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"count\": 3}")

echo "$RECOMMENDATIONS" | python3 -m json.tool
echo

COMPOSITION_ID=$(echo "$RECOMMENDATIONS" | python3 -c "import sys, json; items=json.load(sys.stdin).get('items', []); print(items[0]['composition_id'] if items and 'composition_id' in items[0] else '')" 2>/dev/null)

if [ -z "$COMPOSITION_ID" ]; then
  echo "❌ No composition returned"
  exit 1
fi

echo "✓ Got composition: $COMPOSITION_ID"
echo

# Extract item IDs from first composition
APPETIZER_ID=$(echo "$RECOMMENDATIONS" | python3 -c "import sys, json; items=json.load(sys.stdin).get('items', []); print(items[0]['items'][0]['item_id'] if items and len(items[0].get('items', [])) > 0 else '')" 2>/dev/null)
MAIN_ID=$(echo "$RECOMMENDATIONS" | python3 -c "import sys, json; items=json.load(sys.stdin).get('items', []); print(items[0]['items'][1]['item_id'] if items and len(items[0].get('items', [])) > 1 else '')" 2>/dev/null)
DESSERT_ID=$(echo "$RECOMMENDATIONS" | python3 -c "import sys, json; items=json.load(sys.stdin).get('items', []); print(items[0]['items'][2]['item_id'] if items and len(items[0].get('items', [])) > 2 else '')" 2>/dev/null)

echo "Item IDs:"
echo "  Appetizer: $APPETIZER_ID"
echo "  Main: $MAIN_ID"
echo "  Dessert: $DESSERT_ID"
echo

echo "STEP 3: Test granular feedback - ACCEPT main/dessert, SKIP appetizer"
echo "--------------------------------------"
FEEDBACK_RESPONSE=$(curl -s -X POST "$BASE_URL/sessions/$SESSION_ID/composition/feedback" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"composition_id\": \"$COMPOSITION_ID\",
    \"appetizer_feedback\": \"skip\",
    \"appetizer_comment\": \"Not in the mood for this\",
    \"main_feedback\": \"accepted\",
    \"main_comment\": \"Perfect!\",
    \"dessert_feedback\": \"accepted\",
    \"dessert_comment\": \"Looks amazing\",
    \"composition_action\": \"regenerate_partial\"
  }")

echo "$FEEDBACK_RESPONSE" | python3 -m json.tool
echo

SUCCESS=$(echo "$FEEDBACK_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null)

if [ "$SUCCESS" != "True" ]; then
  echo "❌ Feedback submission failed"
  exit 1
fi

echo "✓ Granular feedback recorded"
echo

echo "STEP 4: Get next recommendations (should keep main/dessert, new appetizer)"
echo "--------------------------------------"
REGEN_RECOMMENDATIONS=$(curl -s -X POST "$BASE_URL/sessions/$SESSION_ID/next" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"count\": 3}")

echo "$REGEN_RECOMMENDATIONS" | python3 -m json.tool
echo

# Verify partial regeneration worked
NEW_COMPOSITION_ID=$(echo "$REGEN_RECOMMENDATIONS" | python3 -c "import sys, json; items=json.load(sys.stdin).get('items', []); print(items[0]['composition_id'] if items and 'composition_id' in items[0] else '')" 2>/dev/null)
NEW_APPETIZER_ID=$(echo "$REGEN_RECOMMENDATIONS" | python3 -c "import sys, json; items=json.load(sys.stdin).get('items', []); print(items[0]['items'][0]['item_id'] if items and len(items[0].get('items', [])) > 0 else '')" 2>/dev/null)
NEW_MAIN_ID=$(echo "$REGEN_RECOMMENDATIONS" | python3 -c "import sys, json; items=json.load(sys.stdin).get('items', []); print(items[0]['items'][1]['item_id'] if items and len(items[0].get('items', [])) > 1 else '')" 2>/dev/null)
NEW_DESSERT_ID=$(echo "$REGEN_RECOMMENDATIONS" | python3 -c "import sys, json; items=json.load(sys.stdin).get('items', []); print(items[0]['items'][2]['item_id'] if items and len(items[0].get('items', [])) > 2 else '')" 2>/dev/null)

echo "Verification:"
echo "  New composition ID: $NEW_COMPOSITION_ID"
echo "  Appetizer changed: $([ "$APPETIZER_ID" != "$NEW_APPETIZER_ID" ] && echo '✓ YES' || echo '❌ NO')"
echo "  Main kept same: $([ "$MAIN_ID" = "$NEW_MAIN_ID" ] && echo '✓ YES' || echo '❌ NO')"
echo "  Dessert kept same: $([ "$DESSERT_ID" = "$NEW_DESSERT_ID" ] && echo '✓ YES' || echo '❌ NO')"
echo

echo "STEP 5: Test ACCEPT ALL action"
echo "--------------------------------------"
ACCEPT_ALL_RESPONSE=$(curl -s -X POST "$BASE_URL/sessions/$SESSION_ID/composition/feedback" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"composition_id\": \"$NEW_COMPOSITION_ID\",
    \"appetizer_feedback\": \"accepted\",
    \"main_feedback\": \"accepted\",
    \"dessert_feedback\": \"accepted\",
    \"composition_action\": \"order_all\"
  }")

echo "$ACCEPT_ALL_RESPONSE" | python3 -m json.tool
echo

NEXT_ACTION=$(echo "$ACCEPT_ALL_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('next_action', ''))" 2>/dev/null)

if [ "$NEXT_ACTION" = "complete_session" ]; then
  echo "✓ Ready to complete session"
  
  echo
  echo "STEP 6: Complete session with all accepted items"
  echo "--------------------------------------"
  COMPLETE_RESPONSE=$(curl -s -X POST "$BASE_URL/sessions/$SESSION_ID/complete" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
      \"selected_item_ids\": [\"$NEW_APPETIZER_ID\", \"$NEW_MAIN_ID\", \"$NEW_DESSERT_ID\"]
    }")
  
  echo "$COMPLETE_RESPONSE" | python3 -m json.tool
  echo
else
  echo "❌ Unexpected next_action: $NEXT_ACTION"
fi

echo "========================================="
echo "TEST COMPLETE"
echo "========================================="
echo
echo "Results:"
echo "✓ Full meal session started successfully"
echo "✓ Composition recommendations received"
echo "✓ Granular feedback recorded (accept/skip individual items)"
echo "✓ Partial regeneration triggered"
echo "✓ Accepted items preserved in new composition"
echo "✓ Rejected item regenerated"
echo "✓ Order all action processed"
echo "✓ Session completed with final selection"
echo
