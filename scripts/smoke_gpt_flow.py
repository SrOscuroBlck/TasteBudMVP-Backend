#!/usr/bin/env python3
import os
import sys
import json
from uuid import uuid4
import time

try:
    import httpx
except ImportError:
    print("httpx not installed in this environment. Please install it or run with the TasteBudBackend venv.")
    sys.exit(1)

BASE_URL = os.environ.get("TASTEBUD_BASE_URL", "http://127.0.0.1:8010/api/v1")


def pretty(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False)


def main():
    user_id = str(uuid4())
    with httpx.Client(timeout=30.0) as client:
        # Health
        r = client.get(f"{BASE_URL}/health")
        print("Health:", r.status_code, r.json())

        # Create a restaurant
        r = client.post(f"{BASE_URL}/restaurants", json={"name": "Test Bistro", "location": "HQ", "tags": ["casual"]})
        r.raise_for_status()
        restaurant = r.json()
        restaurant_id = restaurant["id"]
        print("Restaurant:", pretty(restaurant))

        # Ingest a small menu
        items = [
            {
                "name": "Margherita Pizza",
                "description": "Classic pizza with tomato, mozzarella, and basil",
                "ingredients": ["dough", "tomato", "mozzarella", "basil"],
                "allergens": ["gluten", "lactose"],
                "dietary_tags": ["vegetarian"],
                "cuisine": ["Italian"],
                "price": 12.5,
                "tags": ["cheesy", "baked", "umami"],
            },
            {
                "name": "Spicy Beef Taco",
                "description": "Spicy beef taco",
                "ingredients": ["beef", "chili"],
                "allergens": [],
                "dietary_tags": [],
                "cuisine": ["Mexican"],
                "price": 4.5,
                "tags": ["spicy", "fried", "umami"],
            },
            {
                "name": "Tofu Bowl",
                "description": "Warm tofu and tomato bowl",
                "ingredients": ["tofu", "tomato"],
                "allergens": [],
                "dietary_tags": ["vegan"],
                "cuisine": ["Asian"],
                "price": 9.0,
                "tags": ["hot"],
            },
        ]
        r = client.post(f"{BASE_URL}/restaurants/{restaurant_id}/menu/ingest", json=items)
        r.raise_for_status()
        print("Ingested:", r.json())

        # Start onboarding (creates user if needed)
        r = client.post(f"{BASE_URL}/onboarding/start", json={"user_id": user_id})
        r.raise_for_status()
        question = r.json()
        print("Onboarding question:")
        print(pretty(question))

        # Choose option B if present, else default to A
        qid = question.get("question_id")
        chosen = "B" if any(o.get("id") == "B" for o in question.get("options", [])) else "A"
        if qid:
            r = client.post(
                f"{BASE_URL}/onboarding/answer",
                json={"user_id": user_id, "question_id": qid, "chosen_option_id": chosen},
            )
            r.raise_for_status()
            ans = r.json()
            print("Onboarding answer result:")
            print(pretty(ans))
        else:
            print("No question_id returned; skipping answer step.")

        # Fetch recommendations
        r = client.get(
            f"{BASE_URL}/recommendations",
            params={"user_id": user_id, "restaurant_id": restaurant_id, "top_n": 5},
        )
        r.raise_for_status()
        recs = r.json()
        print("Recommendations (top N):")
        print(pretty(recs))

        # Basic assertions
        ok = True
        items = recs if isinstance(recs, list) else recs.get("items", [])
        if not isinstance(items, list) or len(items) == 0:
            ok = False
            print("ERROR: No recommendations returned.")
        if "prompt" not in question:
            print("WARN: Onboarding question did not include a prompt; GPT may have been unavailable (fallback used).")

        print("\nSmoke test result:", "PASS" if ok else "FAIL")
        print("User ID:", user_id)
        print("Restaurant ID:", restaurant_id)


if __name__ == "__main__":
    main()
