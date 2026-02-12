#!/usr/bin/env python3
"""
Test script for PDF menu ingestion

Usage:
    python test_pdf_ingestion.py <path_to_pdf>

Example:
    python test_pdf_ingestion.py ./test_menu.pdf
"""
import sys
import requests
from pathlib import Path


API_BASE_URL = "http://localhost:8010/api/v1"


def create_test_restaurant():
    url = f"{API_BASE_URL}/ingestion/restaurants"
    data = {
        "name": "Test Restaurant",
        "location": "123 Main St, City",
        "tags": ["italian", "pizza", "pasta"]
    }
    
    response = requests.post(url, json=data)
    if response.status_code == 200:
        restaurant = response.json()
        print(f"✅ Created restaurant: {restaurant['name']} (ID: {restaurant['id']})")
        return restaurant['id']
    else:
        print(f"❌ Failed to create restaurant: {response.text}")
        return None


def upload_pdf(restaurant_id: str, pdf_path: str):
    url = f"{API_BASE_URL}/ingestion/upload/pdf"
    
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"❌ File not found: {pdf_path}")
        return None
    
    print(f"📤 Uploading: {pdf_file.name}")
    
    with open(pdf_file, "rb") as f:
        files = {"file": (pdf_file.name, f, "application/pdf")}
        data = {"restaurant_id": restaurant_id}
        
        response = requests.post(url, files=files, data=data)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Upload successful!")
        print(f"   Upload ID: {result['upload_id']}")
        print(f"   Status: {result['status']}")
        print(f"   Items created: {result['items_created']}")
        print(f"   Processing time: {result['processing_time_seconds']:.2f}s")
        if result.get('error_message'):
            print(f"   Error: {result['error_message']}")
        return result['upload_id']
    else:
        print(f"❌ Upload failed: {response.text}")
        return None


def get_upload_details(upload_id: str):
    url = f"{API_BASE_URL}/ingestion/uploads/{upload_id}"
    response = requests.get(url)
    
    if response.status_code == 200:
        details = response.json()
        print(f"\n📋 Upload Details:")
        print(f"   Status: {details['status']}")
        print(f"   Items created: {details['items_created']}")
        
        if details.get('parsed_data') and details['parsed_data'].get('menu_items'):
            items = details['parsed_data']['menu_items']
            print(f"\n🍽️  Extracted Menu Items ({len(items)}):")
            for i, item in enumerate(items[:5], 1):
                print(f"   {i}. {item['name']}")
                if item.get('price'):
                    print(f"      Price: ${item['price']}")
                if item.get('ingredients'):
                    print(f"      Ingredients: {', '.join(item['ingredients'][:3])}...")
                print()
            
            if len(items) > 5:
                print(f"   ... and {len(items) - 5} more items")
    else:
        print(f"❌ Failed to get upload details: {response.text}")


def list_restaurants():
    url = f"{API_BASE_URL}/ingestion/restaurants"
    response = requests.get(url)
    
    if response.status_code == 200:
        restaurants = response.json()
        print(f"\n🏪 Available Restaurants ({len(restaurants)}):")
        for r in restaurants:
            print(f"   • {r['name']} (ID: {r['id']})")
        return restaurants
    else:
        print(f"❌ Failed to list restaurants: {response.text}")
        return []


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_pdf_ingestion.py <path_to_pdf> [restaurant_id]")
        print("\nIf restaurant_id is not provided, a test restaurant will be created.")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    restaurant_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    print("🚀 TasteBud PDF Ingestion Test\n")
    
    if not restaurant_id:
        restaurant_id = create_test_restaurant()
        if not restaurant_id:
            sys.exit(1)
    
    upload_id = upload_pdf(restaurant_id, pdf_path)
    if upload_id:
        get_upload_details(upload_id)
    
    list_restaurants()


if __name__ == "__main__":
    main()
