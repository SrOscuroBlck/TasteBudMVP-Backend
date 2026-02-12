#!/usr/bin/env python3
"""
Quick test script for PDF menu upload endpoint
"""
import requests
import sys
from pathlib import Path


def test_pdf_upload(pdf_path: str, restaurant_name: str):
    if not Path(pdf_path).exists():
        print(f"❌ PDF file not found: {pdf_path}")
        return
    
    url = "http://localhost:8010/api/v1/menus/upload/pdf"
    
    print(f"\n📄 Uploading menu: {pdf_path}")
    print(f"🏪 Restaurant: {restaurant_name}\n")
    
    with open(pdf_path, "rb") as f:
        files = {"file": (Path(pdf_path).name, f, "application/pdf")}
        data = {"restaurant_name": restaurant_name}
        
        try:
            response = requests.post(url, files=files, data=data, timeout=120)
            
            if response.status_code == 200:
                result = response.json()
                print("✅ Upload successful!")
                print(f"\n📊 Extraction Results:")
                print(f"   Job ID: {result['job_id']}")
                print(f"   Restaurant ID: {result['restaurant_id']}")
                print(f"   Status: {result['status']}")
                print(f"   Items extracted: {result['items_extracted']}")
                print(f"   Processing time: {result.get('processing_time_seconds', 'N/A')}s")
                
                if result.get("items"):
                    print(f"\n🍽️  Sample items extracted:")
                    for i, item in enumerate(result["items"][:3], 1):
                        print(f"\n   {i}. {item['name']}")
                        print(f"      Price: ${item.get('price', 'N/A')}")
                        print(f"      Description: {item.get('description', 'N/A')[:80]}...")
                        if item.get('ingredients'):
                            print(f"      Ingredients: {', '.join(item['ingredients'][:5])}")
                        print(f"      Confidence: {item.get('confidence', 0):.2f}")
                
                if result.get("warnings"):
                    print(f"\n⚠️  Warnings:")
                    for warning in result["warnings"]:
                        print(f"   - {warning}")
                        
            else:
                print(f"❌ Upload failed: {response.status_code}")
                print(response.json())
                
        except requests.exceptions.ConnectionError:
            print("❌ Cannot connect to backend. Is the server running?")
            print("   Run: python -m uvicorn main:app --host 0.0.0.0 --port 8010 --reload")
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_pdf_upload.py <pdf_path> <restaurant_name>")
        print("\nExample:")
        print('  python test_pdf_upload.py ~/Downloads/menu.pdf "Olive Garden"')
        sys.exit(1)
    
    test_pdf_upload(sys.argv[1], sys.argv[2])
