#!/bin/bash
# Backend Verification Script
# This script tests all critical MVP endpoints to ensure backend is working correctly

set -e

BASE_URL="http://localhost:8010/api/v1"
TEST_USER_ID="00000000-0000-0000-0000-000000000001"

echo "======================================"
echo "TasteBud Backend MVP Verification"
echo "======================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test function
test_endpoint() {
    local name=$1
    local method=$2
    local endpoint=$3
    local data=$4
    local expected_status=${5:-200}
    
    echo -n "Testing $name... "
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "$BASE_URL$endpoint")
    else
        response=$(curl -s -w "\n%{http_code}" -X $method "$BASE_URL$endpoint" -H "Content-Type: application/json" -d "$data")
    fi
    
    http_code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" = "$expected_status" ]; then
        echo -e "${GREEN}✓ PASS${NC} (Status: $http_code)"
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} (Expected: $expected_status, Got: $http_code)"
        echo "Response: $body"
        return 1
    fi
}

echo "1. Health Check"
test_endpoint "Health" "GET" "/health"
echo ""

echo "2. Restaurants"
test_endpoint "List Restaurants" "GET" "/restaurants"
echo ""

echo "3. Onboarding Flow"
test_endpoint "Start Onboarding" "POST" "/onboarding/start" '{"user_id":"'$TEST_USER_ID'"}'
echo ""

echo "4. User Profile"
test_endpoint "Get User Profile" "GET" "/users/$TEST_USER_ID/profile" "" "200"
echo ""

echo "5. Search"
test_endpoint "Search Items" "GET" "/search?q=taco&limit=5"
echo ""

echo "6. Get Recommendations (might fail if user has no taste profile)"
test_endpoint "Recommendations" "GET" "/recommendations?user_id=$TEST_USER_ID&top_n=5" "" ""
echo ""

echo "7. Restaurant Details"
# Get first restaurant ID
RESTAURANT_ID=$(curl -s "$BASE_URL/restaurants" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
if [ ! -z "$RESTAURANT_ID" ]; then
    test_endpoint "Restaurant Details" "GET" "/restaurants/$RESTAURANT_ID"
    test_endpoint "Restaurant Menu" "GET" "/restaurants/$RESTAURANT_ID/menu"
else
    echo -e "${RED}✗ SKIP${NC} - No restaurants in database"
fi
echo ""

echo "8. Item Details"
# Get first item ID
ITEM_ID=$(curl -s "$BASE_URL/search?limit=1" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
if [ ! -z "$ITEM_ID" ]; then
    test_endpoint "Item Details" "GET" "/items/$ITEM_ID"
    test_endpoint "Similar Items" "GET" "/items/$ITEM_ID/similar?k=3"
else
    echo -e "${RED}✗ SKIP${NC} - No items in database"
fi
echo ""

echo "9. Feedback"
if [ ! -z "$ITEM_ID" ]; then
    test_endpoint "Submit Rating" "POST" "/feedback/rating" '{"user_id":"'$TEST_USER_ID'","item_id":"'$ITEM_ID'","rating":5,"liked":true,"reasons":["delicious"]}'
    test_endpoint "Quick Like" "POST" "/discovery/quick-like" '{"user_id":"'$TEST_USER_ID'","item_id":"'$ITEM_ID'","liked":true}'
else
    echo -e "${RED}✗ SKIP${NC} - No items for feedback testing"
fi
echo ""

echo "======================================"
echo "Verification Complete!"
echo "======================================"
echo ""
echo "Backend Status Summary:"
echo "- API Base URL: $BASE_URL"
echo "- CORS: Enabled (*)"
echo "- Database: PostgreSQL with pgvector"
echo "- FAISS Index: Check logs above"
echo ""
echo "Frontend Configuration:"
echo "- Update API_BASE_URL in src/services/api/config.ts"
echo "- Current setting should be: http://localhost:8010/api/v1"
echo ""
