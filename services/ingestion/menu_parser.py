from __future__ import annotations
from typing import Dict, Any, List, Optional, cast
from config.settings import settings
from models.ingestion import MenuParsingResult, ParsedMenuItem
import json


class MenuParsingError(Exception):
    pass


class MenuParser:
    def parse_menu_text(self, extracted_text: str, restaurant_name: Optional[str] = None) -> MenuParsingResult:
        if not extracted_text:
            raise ValueError("extracted_text is required to parse menu")
        
        if not extracted_text.strip():
            raise ValueError("extracted_text cannot be empty")
        
        if len(extracted_text.strip()) < 50:
            raise ValueError("extracted_text is too short to be a valid menu")
        
        parsed_data = self._parse_with_llm(extracted_text, restaurant_name)
        
        return self._validate_and_build_result(parsed_data)
    
    def _parse_with_llm(self, menu_text: str, restaurant_name: Optional[str] = None) -> Dict[str, Any]:
        if not settings.OPENAI_API_KEY:
            raise MenuParsingError("OPENAI_API_KEY is not configured")
        
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
        except ImportError:
            raise MenuParsingError("openai package is not installed")
        
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(menu_text, restaurant_name)
        
        try:
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=cast(Any, [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]),
                max_completion_tokens=128000
            )
            
            content = response.choices[0].message.content
            if not content:
                raise MenuParsingError("LLM returned empty response")
            
            parsed_json = json.loads(content.strip())
            return parsed_json
            
        except json.JSONDecodeError as e:
            raise MenuParsingError(f"Failed to parse LLM response as JSON: {str(e)}")
        except Exception as e:
            raise MenuParsingError(f"LLM parsing failed: {str(e)}")
    
    def _build_system_prompt(self) -> str:
        return """You are a professional menu data extraction assistant. Your task is to parse restaurant menu text and return structured JSON.

CRITICAL INSTRUCTIONS:
1. Extract **EVERY SINGLE MENU ITEM** - do not skip any dishes
2. **PRESERVE SECTION CONTEXT IN ITEM NAMES** - if items are under a section header (e.g., "CREPES", "WAFFLES", "PIZZA"), include that category in the item name
3. For each dish, extract: name, description, price, and any visible details
4. Infer ingredients, allergens, dietary tags, cuisine, spice level, cooking method, and course type
5. Use your culinary knowledge to make accurate inferences
6. Return confidence scores (0.0 to 1.0) for each inference
7. If restaurant name or location is mentioned, extract it
8. RETURN PURE JSON ONLY - NO Python code, NO conditionals, NO expressions
9. All values must be JSON primitives: strings, numbers, booleans, arrays, objects
10. DO NOT use ternary operators, if/else expressions, or any programming constructs

SECTION CONTEXT EXAMPLES:

❌ WRONG - Missing section context:
Menu text: "CREPES\nJamón y Queso $18.90\nQueso $13.90"
Bad extraction: {"name": "Jamón y Queso"}, {"name": "Queso"}

✅ CORRECT - Preserves section in name:
Menu text: "CREPES\nJamón y Queso $18.90\nQueso $13.90"
Good extraction: {"name": "Crepe de Jamón y Queso"}, {"name": "Crepe de Queso"}

❌ WRONG - Missing context:
Menu text: "WAFFLES\nMantequilla y Syrup $9.90"
Bad extraction: {"name": "Mantequilla y Syrup"}

✅ CORRECT:
Menu text: "WAFFLES\nMantequilla y Syrup $9.90"
Good extraction: {"name": "Waffle con Mantequilla y Syrup"}

OUTPUT FORMAT (strict JSON):
{
  "restaurant_name": "string or null",
  "restaurant_location": "string or null",
  "menu_items": [
    {
      "name": "Dish Name WITH Section Context",
      "description": "Description if available",
      "price": 12.99 or null,
      "ingredients": ["ingredient1", "ingredient2"],
      "allergens": ["dairy", "nuts", "shellfish"],
      "dietary_tags": ["vegetarian", "gluten-free", "vegan"],
      "cuisine": ["italian", "asian"],
      "spice_level": 0-5 or null,
      "cooking_method": "grilled" or null,
      "course": "appetizer" or "main" or "dessert" or null,
      "inference_confidence": 0.85,
      "raw_text": "original text snippet"
    }
  ],
  "extraction_confidence": 0.90,
  "notes": "any extraction issues or notes"
}

RULES:
- Only include actual food items, not headers or sections
- Allergens: common allergens only (dairy, eggs, fish, shellfish, nuts, peanuts, wheat, soy)
- Dietary tags: vegetarian, vegan, gluten-free, dairy-free, nut-free, halal, kosher
- Spice level: 0 (not spicy) to 5 (very spicy)
- Course: appetizer, main, side, dessert, beverage
- If price has multiple values (e.g., sizes), use the base/smallest price
- Normalize ingredient names (e.g., "tomatoes" not "fresh vine-ripened tomatoes")
- EMPTY arrays [] not conditional arrays
- Return ONLY valid JSON, no markdown, no code blocks, no explanations"""
    
    def _build_user_prompt(self, menu_text: str, restaurant_name: Optional[str] = None) -> str:
        prompt = "Parse this restaurant menu:\n\n"
        
        if restaurant_name:
            prompt += f"Restaurant: {restaurant_name}\n\n"
        
        prompt += f"MENU TEXT:\n{menu_text}\n\n"
        prompt += "Return structured JSON following the exact format specified."
        
        return prompt
    
    def _validate_and_build_result(self, parsed_data: Dict[str, Any]) -> MenuParsingResult:
        if "menu_items" not in parsed_data:
            raise MenuParsingError("Parsed data missing required field: menu_items")
        
        raw_items = parsed_data.get("menu_items", [])
        if not isinstance(raw_items, list):
            raise MenuParsingError("menu_items must be a list")
        
        menu_items = []
        for item_data in raw_items:
            if not isinstance(item_data, dict):
                continue
            
            if "name" not in item_data or not item_data["name"]:
                continue
            
            try:
                parsed_item = ParsedMenuItem(
                    name=item_data["name"],
                    description=item_data.get("description", ""),
                    price=self._extract_price(item_data.get("price")),
                    ingredients=self._normalize_list(item_data.get("ingredients", [])),
                    allergens=self._normalize_list(item_data.get("allergens", [])),
                    dietary_tags=self._normalize_list(item_data.get("dietary_tags", [])),
                    cuisine=self._normalize_list(item_data.get("cuisine", [])),
                    spice_level=self._extract_spice_level(item_data.get("spice_level")),
                    cooking_method=item_data.get("cooking_method"),
                    course=item_data.get("course"),
                    inference_confidence=float(item_data.get("inference_confidence", 0.8)),
                    raw_text=item_data.get("raw_text")
                )
                menu_items.append(parsed_item)
            except Exception:
                continue
        
        if not menu_items:
            raise MenuParsingError("No valid menu items were extracted from the text")
        
        return MenuParsingResult(
            restaurant_name=parsed_data.get("restaurant_name"),
            restaurant_location=parsed_data.get("restaurant_location"),
            menu_items=menu_items,
            extraction_confidence=float(parsed_data.get("extraction_confidence", 0.8)),
            notes=parsed_data.get("notes", "")
        )
    
    def _extract_price(self, price_value: Any) -> Optional[float]:
        if price_value is None:
            return None
        
        if isinstance(price_value, (int, float)):
            return float(price_value)
        
        if isinstance(price_value, str):
            try:
                cleaned = price_value.replace("$", "").replace("€", "").replace("£", "").strip()
                return float(cleaned)
            except ValueError:
                return None
        
        return None
    
    def _extract_spice_level(self, spice_value: Any) -> Optional[int]:
        if spice_value is None:
            return None
        
        if isinstance(spice_value, int):
            return max(0, min(5, spice_value))
        
        if isinstance(spice_value, str):
            try:
                level = int(spice_value)
                return max(0, min(5, level))
            except ValueError:
                return None
        
        return None
    
    def _normalize_list(self, items: Any) -> List[str]:
        if not isinstance(items, list):
            return []
        
        normalized = []
        for item in items:
            if isinstance(item, str) and item.strip():
                normalized.append(item.strip().lower())
        
        return normalized
