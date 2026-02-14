#!/usr/bin/env python3
"""
Test script to demonstrate course-based recommendation improvements.

Shows the difference between:
1. Default recommendations (now prioritizes FOOD over drinks)
2. Explicit beverage recommendations (when user wants drinks)
3. How business logic now influences results
"""

import requests
import json
from typing import Dict, Any

API_BASE = "http://localhost:8010/api/v1"
USER_ID = "385b70e4-35f6-4d8e-9113-d1ef1672afec"
RESTAURANT_ID = "b62a20c0-3742-4083-b8f7-ebaf91bf0b12"


def get_auth_token(email: str = "test@test.com") -> str:
    """Get authentication token for testing."""
    print(f"\n🔐 Getting auth token for {email}...")
    
    response = requests.post(
        f"{API_BASE}/auth/request-otp",
        json={"email": email}
    )
    
    if response.status_code != 200:
        print(f"❌ Failed to request OTP: {response.text}")
        return None
    
    print("📧 OTP sent. Enter the code from your email:")
    otp = input("OTP code: ").strip()
    
    verify_response = requests.post(
        f"{API_BASE}/auth/verify-otp",
        json={"email": email, "otp_code": otp}
    )
    
    if verify_response.status_code != 200:
        print(f"❌ Failed to verify OTP: {verify_response.text}")
        return None
    
    data = verify_response.json()
    token = data.get("access_token")
    print("✅ Authentication successful")
    return token


def test_recommendations(
    token: str,
    course_preference: str = None,
    top_n: int = 10,
    label: str = "Default"
) -> Dict[str, Any]:
    """Get recommendations with optional course filtering."""
    
    params = {
        "restaurant_id": RESTAURANT_ID,
        "top_n": top_n
    }
    
    if course_preference:
        params["course_preference"] = course_preference
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"\n{'='*80}")
    print(f"🎯 {label}")
    print(f"{'='*80}")
    if course_preference:
        print(f"📋 Course Preference: {course_preference}")
    else:
        print(f"📋 Course Preference: None (default behavior - should prioritize FOOD)")
    print()
    
    response = requests.get(
        f"{API_BASE}/recommendations",
        params=params,
        headers=headers
    )
    
    if response.status_code != 200:
        print(f"❌ Failed to get recommendations: {response.text}")
        return None
    
    result = response.json()
    items = result.get("items", [])
    
    if not items:
        print("⚠️  No recommendations returned")
        return result
    
    # Analyze results by course
    course_counts = {}
    for item in items:
        course = item.get("course", "unknown")
        course_counts[course] = course_counts.get(course, 0) + 1
    
    print(f"📊 Course Distribution (Total: {len(items)} items):")
    for course, count in sorted(course_counts.items()):
        percentage = (count / len(items)) * 100
        print(f"   {course:15} : {count:2} items ({percentage:5.1f}%)")
    print()
    
    # Show top 10 items with details
    print(f"🍽️  Top {min(10, len(items))} Recommendations:")
    print(f"{'#':<3} {'Name':<50} {'Course':<12} {'Score':<7} {'Course Adj'}")
    print("-" * 100)
    
    for i, item in enumerate(items[:10], 1):
        name = item["name"][:47] + "..." if len(item["name"]) > 50 else item["name"]
        course = item.get("course", "N/A") or "N/A"
        score = item["score"]
        
        # Extract course adjustment from ranking factors
        ranking_factors = item.get("ranking_factors", {})
        course_adj = ranking_factors.get("course_adjustment", 0.0)
        course_adj_str = f"{course_adj:+.2f}" if course_adj != 0 else "  0.00"
        
        print(f"{i:<3} {name:<50} {course:<12} {score:<7.3f} {course_adj_str}")
    
    return result


def show_reasoning_example(token: str):
    """Show detailed reasoning for a specific recommendation."""
    print(f"\n{'='*80}")
    print(f"🧠 REASONING EXAMPLE: How Course Adjustments Work")
    print(f"{'='*80}")
    
    params = {
        "restaurant_id": RESTAURANT_ID,
        "top_n": 3
    }
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(
        f"{API_BASE}/recommendations",
        params=params,
        headers=headers
    )
    
    if response.status_code != 200:
        print(f"❌ Failed to get recommendations: {response.text}")
        return
    
    result = response.json()
    items = result.get("items", [])
    
    if not items:
        print("⚠️  No recommendations returned")
        return
    
    item = items[0]
    print(f"\n🍽️  Example Item: {item['name']}")
    print(f"   Course: {item.get('course', 'N/A')}")
    print(f"   Final Score: {item['score']:.3f}")
    print()
    print("📈 Ranking Factor Breakdown:")
    
    ranking_factors = item.get("ranking_factors", {})
    for factor, value in sorted(ranking_factors.items()):
        emoji = "✅" if value > 0 else "❌" if value < 0 else "➖"
        print(f"   {emoji} {factor:30} : {value:+.3f}")
    
    print()
    print("💡 Explanation:")
    print(f"   {item.get('reason', 'No explanation available')}")


def main():
    print("=" * 80)
    print("🚀 COURSE-BASED RECOMMENDATION TESTING")
    print("=" * 80)
    print()
    print("This test demonstrates the new course filtering and prioritization logic.")
    print()
    print("KEY IMPROVEMENTS:")
    print("1. Default behavior prioritizes FOOD (main, appetizers) over beverages")
    print("2. Beverages get -0.5 penalty by default (unless explicitly requested)")
    print("3. Condiments/pantry items get -0.6 penalty (almost never recommended)")
    print("4. Users can explicitly request beverages using course_preference parameter")
    print()
    
    # Get authentication token
    token = get_auth_token()
    if not token:
        print("❌ Authentication failed. Exiting.")
        return
    
    # Test 1: Default recommendations (should prioritize food)
    test_recommendations(
        token=token,
        course_preference=None,
        label="TEST 1: Default Recommendations (Food Priority)"
    )
    
    input("\n⏸️  Press Enter to continue to next test...")
    
    # Test 2: Explicitly request beverages
    test_recommendations(
        token=token,
        course_preference="beverage",
        label="TEST 2: Explicit Beverage Request"
    )
    
    input("\n⏸️  Press Enter to continue to next test...")
    
    # Test 3: Main course only
    test_recommendations(
        token=token,
        course_preference="main",
        label="TEST 3: Main Course Only"
    )
    
    input("\n⏸️  Press Enter to see reasoning example...")
    
    # Show reasoning
    show_reasoning_example(token)
    
    print("\n" + "=" * 80)
    print("✅ Testing Complete!")
    print("=" * 80)
    print()
    print("SUMMARY:")
    print("• The system now applies business logic, not just vector similarity")
    print("• Beverages are deprioritized by default (-0.5 adjustment)")
    print("• Users get food recommendations unless they explicitly ask for drinks")
    print("• This creates a more realistic and useful recommendation experience")
    print()


if __name__ == "__main__":
    main()
