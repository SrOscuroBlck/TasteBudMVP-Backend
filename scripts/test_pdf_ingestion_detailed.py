#!/usr/bin/env python3
"""
Detailed PDF Ingestion Test
Shows every step of the pipeline with full visibility into data transformations
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from config.settings import settings
from services.ingestion.pdf_processor import PDFProcessor
from services.ingestion.menu_parser import MenuParser


def print_section(title: str, content: str, max_lines: int = None):
    print("\n" + "="*80, flush=True)
    print(f" {title}", flush=True)
    print("="*80, flush=True)
    if max_lines:
        lines = content.split("\n")
        if len(lines) > max_lines:
            print("\n".join(lines[:max_lines]), flush=True)
            print(f"\n... ({len(lines) - max_lines} more lines) ...", flush=True)
            print("\n".join(lines[-5:]), flush=True)
        else:
            print(content, flush=True)
    else:
        print(content, flush=True)


def test_pdf_ingestion(pdf_path: str, restaurant_name: str = "Test Restaurant"):
    print("\n" + "🔍 PDF INGESTION DETAILED TEST" + "\n", flush=True)
    print(f"PDF Path: {pdf_path}", flush=True)
    print(f"Restaurant: {restaurant_name}", flush=True)
    
    # STEP 1: PDF Text Extraction
    print_section("STEP 1: PDF TEXT EXTRACTION", "")
    pdf_processor = PDFProcessor()
    
    try:
        extracted_text = pdf_processor.extract_text_from_pdf(pdf_path)
        print(f"✅ Successfully extracted {len(extracted_text)} characters", flush=True)
        print(f"   Line count: {len(extracted_text.splitlines())}", flush=True)
        print(f"   Word count: {len(extracted_text.split())}", flush=True)
        
        print_section("EXTRACTED TEXT (First 2000 chars)", extracted_text[:2000])
        
        # Show validation
        is_valid = pdf_processor.validate_extracted_text(extracted_text)
        if is_valid:
            print("\n✅ Text validation: PASSED", flush=True)
        else:
            print("\n❌ Text validation: FAILED (too short or too few words)", flush=True)
            return
        
    except Exception as e:
        print(f"\n❌ PDF extraction failed: {str(e)}", flush=True)
        return
    
    # STEP 2: Prompt Construction
    print_section("STEP 2: LLM PROMPT CONSTRUCTION", "")
    menu_parser = MenuParser()
    
    # Show the system prompt
    print("SYSTEM PROMPT:", flush=True)
    print("-" * 80, flush=True)
    system_prompt = menu_parser._build_system_prompt()
    print(system_prompt[:1500], flush=True)
    print("\n... (truncated for brevity)", flush=True)
    
    # Show the user prompt
    print("\n\nUSER PROMPT:", flush=True)
    print("-" * 80, flush=True)
    user_prompt = menu_parser._build_user_prompt(extracted_text, restaurant_name)
    print(f"Restaurant Name: {restaurant_name}", flush=True)
    print(f"Menu Text Length: {len(extracted_text)} characters", flush=True)
    print(f"User Prompt Length: {len(user_prompt)} characters", flush=True)
    print("\nFirst 1500 characters of user prompt:", flush=True)
    print(user_prompt[:1500], flush=True)
    print("\n... (full text sent to GPT)", flush=True)
    
    # STEP 3: GPT API Call
    print_section("STEP 3: SENDING TO gpt-5-mini", "")
    print(f"Model: {settings.OPENAI_MODEL}", flush=True)
    print(f"Max completion tokens: 50000", flush=True)
    print(f"Temperature: default (1.0)", flush=True)
    print("\n⏳ Calling OpenAI API... (this may take 30-60 seconds)", flush=True)
    
    import time
    start_time = time.time()
    
    try:
        parsing_result = menu_parser.parse_menu_text(extracted_text, restaurant_name)
        elapsed = time.time() - start_time
        print(f"\n✅ GPT response received successfully in {elapsed:.1f} seconds", flush=True)
        
    except Exception as e:
        print(f"\n❌ GPT parsing failed: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return
    
    # STEP 4: GPT Response Analysis
    print_section("STEP 4: GPT RESPONSE ANALYSIS", "")
    
    print(f"Items extracted: {len(parsing_result.menu_items)}", flush=True)
    print(f"Restaurant name inferred: {parsing_result.restaurant_name or 'Not extracted'}", flush=True)
    
    # Show raw JSON structure (handle both Pydantic v1 and v2)
    try:
        result_dict = parsing_result.model_dump()
    except AttributeError:
        result_dict = parsing_result.dict()
    
    print("\n\nPARSED RESULT (JSON - First 5 items):", flush=True)
    print("-" * 80, flush=True)
    preview_result = {
        "restaurant_name": result_dict.get("restaurant_name"),
        "menu_items": result_dict.get("menu_items", [])[:5]
    }
    print(json.dumps(preview_result, indent=2, ensure_ascii=False), flush=True)
    print(f"\n... (showing first 5 of {len(parsing_result.menu_items)} items)", flush=True)
    
    # STEP 5: Item-by-Item Breakdown
    print_section("STEP 5: EXTRACTED MENU ITEMS BREAKDOWN", "")
    
    for idx, item in enumerate(parsing_result.menu_items, 1):
        print(f"\n{idx}. {item.name}")
        print(f"   Price: ${item.price}" if item.price else "   Price: Not specified")
        print(f"   Description: {item.description[:100]}..." if item.description and len(item.description) > 100 else f"   Description: {item.description}")
        print(f"   Ingredients: {', '.join(item.ingredients[:5])}" + (" ..." if len(item.ingredients) > 5 else ""))
        print(f"   Cuisine: {', '.join(item.cuisine)}")
        print(f"   Course: {item.course}")
        print(f"   Allergens: {', '.join(item.allergens)}")
        print(f"   Dietary tags: {', '.join(item.dietary_tags)}")
        print(f"   Confidence: {item.inference_confidence}")
    
    # STEP 6: Quality Analysis
    print_section("STEP 6: QUALITY ANALYSIS", "")
    
    total_items = len(parsing_result.menu_items)
    items_with_prices = sum(1 for item in parsing_result.menu_items if item.price is not None)
    items_with_descriptions = sum(1 for item in parsing_result.menu_items if item.description)
    items_with_ingredients = sum(1 for item in parsing_result.menu_items if item.ingredients)
    
    print(f"Total items extracted: {total_items}")
    print(f"Items with prices: {items_with_prices} ({items_with_prices/total_items*100:.1f}%)")
    print(f"Items with descriptions: {items_with_descriptions} ({items_with_descriptions/total_items*100:.1f}%)")
    print(f"Items with ingredients: {items_with_ingredients} ({items_with_ingredients/total_items*100:.1f}%)")
    
    # Check for naming issues
    print("\n⚠️  NAMING QUALITY CHECK:")
    short_names = [item.name for item in parsing_result.menu_items if len(item.name.split()) <= 2]
    if short_names:
        print(f"   Found {len(short_names)} items with very short names (≤2 words):")
        for name in short_names[:10]:
            print(f"   - {name}")
        print("\n   💡 These may be missing section context (e.g., 'Jamón y Queso' vs 'Crepe de Jamón y Queso')")
    else:
        print("   ✅ All items have descriptive names")
    
    # STEP 7: Recommendations
    print_section("STEP 7: RECOMMENDATIONS FOR IMPROVEMENT", "")
    
    issues = []
    
    if total_items < 30:
        issues.append(f"Only {total_items} items extracted - the menu likely has more items")
    
    if items_with_prices / total_items < 0.8:
        issues.append(f"Only {items_with_prices/total_items*100:.1f}% of items have prices")
    
    if len(short_names) > total_items * 0.3:
        issues.append(f"{len(short_names)} items ({len(short_names)/total_items*100:.1f}%) have short names - likely missing section context")
    
    if issues:
        print("⚠️  Issues detected:")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
        
        print("\n💡 Suggested fixes:")
        print("   1. Improve prompt to preserve section headers in item names")
        print("   2. Increase context window or chunk large menus")
        print("   3. Add validation for minimum items extracted")
        print("   4. Use few-shot examples showing proper item naming")
    else:
        print("✅ No major issues detected!")
    
    print("\n" + "="*80)
    print(" TEST COMPLETE")
    print("="*80)
    print(f"\nExtracted {total_items} menu items from {len(extracted_text)} characters of text\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_pdf_ingestion_detailed.py <pdf_path> [restaurant_name]")
        print("\nExample:")
        print("  python test_pdf_ingestion_detailed.py uploads/menus/menu.pdf 'Crepes & Waffles'")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    restaurant_name = sys.argv[2] if len(sys.argv) > 2 else "Test Restaurant"
    
    if not Path(pdf_path).exists():
        print(f"❌ Error: File not found: {pdf_path}")
        sys.exit(1)
    
    test_pdf_ingestion(pdf_path, restaurant_name)
