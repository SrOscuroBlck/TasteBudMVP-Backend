from __future__ import annotations
from typing import Dict, Any, List, Optional, cast
from config.settings import settings
from models.ingestion import MenuParsingResult, ParsedMenuItem
import json


class MenuParsingError(Exception):
    pass


class MenuParser:
    def parse_menu_text(self, extracted_text: str, restaurant_name: Optional[str] = None, currency: Optional[str] = None) -> MenuParsingResult:
        if not extracted_text:
            raise ValueError("extracted_text is required to parse menu")
        
        if not extracted_text.strip():
            raise ValueError("extracted_text cannot be empty")
        
        if len(extracted_text.strip()) < 50:
            raise ValueError("extracted_text is too short to be a valid menu")
        
        self.currency = currency  # Store for price conversion
        parsed_data = self._parse_with_llm(extracted_text, restaurant_name, currency)
        
        return self._validate_and_build_result(parsed_data)
    
    def _parse_with_llm(self, menu_text: str, restaurant_name: Optional[str] = None, currency: Optional[str] = None) -> Dict[str, Any]:
        if not settings.OPENAI_API_KEY:
            raise MenuParsingError("OPENAI_API_KEY is not configured")
        
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
        except ImportError:
            raise MenuParsingError("openai package is not installed")
        
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(menu_text, restaurant_name, currency)
        
        try:
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=cast(Any, [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]),
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            if not content:
                raise MenuParsingError("LLM returned empty response")
            
            # Clean up common JSON formatting issues
            content_clean = content.strip()
            
            # Remove markdown code blocks if present
            if content_clean.startswith("```json"):
                content_clean = content_clean[7:]
            if content_clean.startswith("```"):
                content_clean = content_clean[3:]
            if content_clean.endswith("```"):
                content_clean = content_clean[:-3]
            
            content_clean = content_clean.strip()
            
            parsed_json = json.loads(content_clean)
            return parsed_json
            
        except json.JSONDecodeError as e:
            # Log the actual content for debugging
            print(f"JSON parsing failed at position {e.pos}: {e.msg}")
            if content:
                # Show context around the error
                start = max(0, e.pos - 100)
                end = min(len(content), e.pos + 100)
                print(f"Context around error: ...{content[start:end]}...")
            raise MenuParsingError(f"Failed to parse LLM response as JSON: {str(e)}")
        except Exception as e:
            raise MenuParsingError(f"LLM parsing failed: {str(e)}")
    
    def _build_system_prompt(self) -> str:
        return """You are a professional menu data extraction assistant. Your task is to parse restaurant menu text and return structured JSON.

CRITICAL NAMING RULE - READ THIS FIRST:
When you extract a dish name, ask yourself: "Would a customer understand what this is WITHOUT seeing the menu section?"
- If NO → Add the section context naturally (e.g., "Queso" → "Crepe de Queso")
- If YES → Use the name as-is (e.g., "Coca-Cola", "Pancakes de Ahuyama")

IMPORTANT: Keep names in their ORIGINAL LANGUAGE from the menu. Do NOT translate names to English.

THIS IS THE #1 MOST IMPORTANT RULE. Names must be clear and unambiguous.

EXAMPLES OF CORRECT NAME EXTRACTION:

Menu section: "CREPES SALADOS"
Items listed: "Jamón y Queso $18.90", "Queso $13.90", "Champiñones, Alcachofa y Queso $21.90"
✅ CORRECT OUTPUT:
{"name": "Crepe de Jamón y Queso", "description": "..."}
{"name": "Crepe de Queso", "description": "..."}
{"name": "Crepe de Champiñones, Alcachofa y Queso", "description": "..."}
WHY: Without "Crepe de", users wouldn't know these are crepes.

Menu section: "HUEVOS"
Items listed: "Poché $12.90", "Revueltos $11.90"
✅ CORRECT OUTPUT:
{"name": "Huevos Poché", "description": "..."}
{"name": "Huevos Revueltos", "description": "..."}
WHY: "Poché" alone doesn't tell users it's eggs.

Menu section: "WAFFLES"
Items listed: "Mantequilla y Syrup $9.90", "Fresas y Crema $13.90"
✅ CORRECT OUTPUT:
{"name": "Waffle de Mantequilla y Syrup", "description": "..."}
{"name": "Waffle de Fresas y Crema", "description": "..."}
WHY: Without "Waffle de", these just sound like ingredient lists.

Menu section: "BEBIDAS"
Items listed: "Coca-Cola $3.50", "Jugo de Naranja Natural $5.90"
✅ CORRECT OUTPUT:
{"name": "Coca-Cola", "description": "..."}
{"name": "Jugo de Naranja Natural", "description": "..."}
WHY: "Coca-Cola" is already clear. "Jugo de Naranja Natural" already says it's juice.

Menu section: "DESAYUNOS"
Items listed: "Pancakes de Ahuyama $8.90"
✅ CORRECT OUTPUT:
{"name": "Pancakes de Ahuyama", "description": "..."}
WHY: "Pancakes de Ahuyama" is already clear - no need to add "Desayuno de".

❌ WRONG - Missing context:
{"name": "Queso"} - What is this? Cheese? A cheese dish?
{"name": "Poché"} - Poached what?
{"name": "Jamón y Queso"} - Ham and cheese what? Sandwich? Crepe?
{"name": "Mantequilla y Syrup"} - This is just ingredients, not a dish name

❌ WRONG - Technical annotations:
{"name": "Queso (header repeat)"}
{"name": "CREPES - Jamón y Queso"}
{"name": "Section: Waffles"}

OTHER CRITICAL INSTRUCTIONS:
1. Extract **EVERY SINGLE MENU ITEM** - do not skip any dishes
2. **NO TECHNICAL ANNOTATIONS** - do not add "(header repeat)", "section:", or meta-text
3. For each dish, extract: name, description, price, and any visible details
4. **ALWAYS provide ingredients and allergens** - use culinary knowledge to infer them from dish name/description
   - Even if not explicitly listed, infer obvious ingredients (e.g., "Crepe de Jamón y Queso" → ["jamón", "queso", "crepe"])
   - Identify allergens from ingredients (e.g., dairy, eggs, wheat, nuts, shellfish, fish, soy, peanuts)
5. Infer dietary tags, cuisine, spice level, cooking method, and course type
6. Return confidence scores (0.0 to 1.0) - **vary the confidence based on how certain you are**
7. If restaurant name or location is mentioned, extract it
8. RETURN PURE JSON ONLY - NO Python code, NO conditionals, NO expressions
9. All values must be JSON primitives: strings, numbers, booleans, arrays, objects

OUTPUT FORMAT (strict JSON):
{
  "restaurant_name": "string or null",
  "restaurant_location": "string or null",
  "currency": "USD, COP, EUR, etc. or null",
  "menu_items": [
    {
      "name": "Exact dish name from menu IN ORIGINAL LANGUAGE",
      "description": "English description of what the dish is, ingredients, how it's served",
      "price": 12.99 or null,
      "ingredients": ["ingredient1", "ingredient2"],
      "allergens": ["dairy", "nuts", "shellfish"],
      "dietary_tags": ["vegetarian", "gluten-free", "vegan"],
      "cuisine": ["italian", "asian"],
      "spice_level": 0-5 or null,
      "cooking_method": "grilled" or null,
      "course": "appetizer" or "main" or "dessert" or "breakfast" or "beverage" or null,
      "inference_confidence": 0.85,
      "raw_text": "original text snippet"
    }
  ],
  "extraction_confidence": 0.90,
  "notes": "any extraction issues or notes"
}

DESCRIPTION FIELD REQUIREMENTS:
**ALL DESCRIPTIONS MUST BE IN ENGLISH** - even if the menu and dish names are in another language.

✅ GOOD descriptions (in English):
- "Crepe filled with ham and melted cheese" (describes what it is)
- "Poached eggs served with toast" (tells what you get)
- "Grilled chicken breast with vegetables" (explains the dish)
- "Belgian waffle topped with butter and maple syrup" (describes components)
- "Sandwich with hearts of palm on toasted bread" (describes unfamiliar ingredients)

❌ BAD descriptions (DO NOT DO THIS):
- "Palmitos $33.300" (this is just raw menu text!)
- "Jamón y Queso $18.90" (just repeating the menu line!)
- "Crepe con jamón y queso" (this is just a translation of the name, not a description!)
- "" (empty is better than copying raw text)

If the menu provides NO description context at all, generate a brief English description based on the dish name and ingredients.
NEVER just copy the menu price line or translate the name into the description field.
The description should explain what the dish IS and how it's prepared/served.

ADDITIONAL RULES:
- Follow the CRITICAL NAMING RULE above - add section context when names are ambiguous
- NO technical annotations or meta-text in names
- Use description field for additional details
- Only include actual food items, not section headers
- **EXCLUDE retail products** (packaged batter, take-home items, merchandise)
- **Cuisine naming**: Use simple cuisine names (e.g., "italian", "mexican", "asian") - NO "-inspired", "-style", or "-fusion" suffixes
- Allergens: common allergens only (dairy, eggs, fish, shellfish, nuts, peanuts, wheat, soy)
- Dietary tags: vegetarian, vegan, gluten-free, dairy-free, nut-free, halal, kosher
- Spice level: 0 (not spicy) to 5 (very spicy)
- Course: breakfast, appetizer, main, side, dessert, beverage
- If price has multiple values (e.g., sizes), use the base/smallest price
- Normalize ingredient names (e.g., "tomatoes" not "fresh vine-ripened tomatoes")
- Detect currency symbols: $ (USD or local), € (EUR), £ (GBP), $ with COP context (Colombian Pesos)
- EMPTY arrays [] not conditional arrays
- Return ONLY valid JSON, no markdown, no code blocks, no explanations
- **EXTRACT EVERY SINGLE DISH** - do not skip items even if the JSON is getting long

CRITICAL JSON FORMATTING RULES:
1. Every object {} must have properly closed braces
2. Every array [] must have properly closed brackets
3. Use commas between array items: [item1, item2, item3]
4. Use commas between object properties: {"key1": "value", "key2": "value"}
5. NO trailing commas: {"key": "value"} NOT {"key": "value",}
6. Strings must be in double quotes: "text" NOT 'text'
7. Escape quotes inside strings: "He said \"hello\"" 
8. Numbers without quotes: 12.99 NOT "12.99"
9. Booleans without quotes: true NOT "true"
10. Arrays must be valid: ["item1", "item2"] NOT ["item1" "item2"]
11. Check ALL commas, brackets, and braces before finishing"""
    
    def _build_user_prompt(self, menu_text: str, restaurant_name: Optional[str] = None, currency: Optional[str] = None) -> str:
        prompt = "Parse this restaurant menu:\n\n"
        
        if restaurant_name:
            prompt += f"Restaurant: {restaurant_name}\n\n"
        
        if currency:
            prompt += f"IMPORTANT: Menu prices are in {currency}. Extract prices as they appear and include '{currency}' in the currency field.\n\n"
        
        prompt += "CRITICAL REMINDERS:\n"
        prompt += "1. NAMING: Keep names in ORIGINAL LANGUAGE. Add section context when ambiguous (e.g., 'Queso' → 'Crepe de Queso', 'Poché' → 'Huevos Poché')\n"
        prompt += "2. DESCRIPTIONS: Write ALL descriptions in ENGLISH. Describe what the dish is, not just translate the name.\n"
        prompt += "3. JSON FORMATTING: Check all commas, brackets, braces. No trailing commas. Valid array syntax.\n\n"
        
        prompt += f"MENU TEXT:\n{menu_text}\n\n"
        prompt += "Return structured JSON following the exact format specified.\n"
        prompt += "FINAL CHECK: Verify JSON is valid - all brackets/braces match, commas in right places, no trailing commas."
        
        return prompt
    
    def _validate_and_build_result(self, parsed_data: Dict[str, Any]) -> MenuParsingResult:
        if "menu_items" not in parsed_data:
            raise MenuParsingError("Parsed data missing required field: menu_items")
        
        raw_items = parsed_data.get("menu_items", [])
        if not isinstance(raw_items, list):
            raise MenuParsingError("menu_items must be a list")
        
        menu_items = []
        skipped_count = 0
        
        for item_data in raw_items:
            if not isinstance(item_data, dict):
                continue
            
            if "name" not in item_data or not item_data["name"]:
                skipped_count += 1
                continue
            
            try:
                # Extract and validate price - SKIP items with no price or 0 price
                price = self._extract_price(item_data.get("price"))
                if price is None or price <= 0:
                    skipped_count += 1
                    continue
                
                parsed_item = ParsedMenuItem(
                    name=item_data["name"],
                    description=item_data.get("description", ""),
                    price=price,
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
                skipped_count += 1
                continue
        
        if not menu_items:
            raise MenuParsingError("No valid menu items were extracted from the text")
        
        notes = parsed_data.get("notes", "")
        if skipped_count > 0:
            notes += f" (Skipped {skipped_count} invalid items: no price or zero price)"
        
        return MenuParsingResult(
            restaurant_name=parsed_data.get("restaurant_name"),
            restaurant_location=parsed_data.get("restaurant_location"),
            menu_items=menu_items,
            extraction_confidence=float(parsed_data.get("extraction_confidence", 0.8)),
            notes=notes
        )
    
    def _extract_price(self, price_value: Any) -> Optional[float]:
        if price_value is None:
            return None
        
        raw_price = 0.0
        if isinstance(price_value, (int, float)):
            raw_price = float(price_value)
        elif isinstance(price_value, str):
            try:
                cleaned = price_value.replace("$", "").replace("€", "").replace("£", "").replace(",", "").strip()
                raw_price = float(cleaned)
            except ValueError:
                return None
        else:
            return None
        
        # Convert to USD if currency is not USD
        if hasattr(self, 'currency') and self.currency:
            return self._convert_to_usd(raw_price, self.currency)
        
        return raw_price
    
    def _convert_to_usd(self, amount: float, currency: str) -> float:
        """Convert amount from given currency to USD using free exchangerate-api.com."""
        if not currency or currency.upper() == "USD":
            return amount
        
        try:
            import requests
            
            currency_upper = currency.upper()
            
            # Use free exchangerate-api.com (no rate limits, 1h cache)
            response = requests.get(
                f'https://api.exchangerate-api.com/v4/latest/{currency_upper}',
                timeout=5
            )
            response.raise_for_status()
            
            data = response.json()
            rate_to_usd = data['rates']['USD']
            usd_amount = amount * rate_to_usd
            
            return round(usd_amount, 2)
            
        except Exception as e:
            print(f"Currency conversion API failed: {e}")
            # Return None to trigger validation skip if conversion fails
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
