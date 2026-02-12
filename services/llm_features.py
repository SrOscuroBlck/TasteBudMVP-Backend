"""LLM-powered taste profile generation for menu items."""

from typing import Dict, Optional, List
import json
from openai import OpenAI
from config.settings import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

TASTE_PROFILE_SYSTEM_PROMPT = """You are a culinary expert analyzing menu items to generate taste profiles.

Given a menu item, generate a taste profile with these 10 taste axes (values 0.0-1.0):
- sweet: sweetness level
- sour: sourness/tartness level  
- salty: saltiness level
- bitter: bitterness level
- umami: savory/umami level
- spicy: heat/spice level
- fattiness: richness/fat content
- acidity: acidic/citrus level
- crunch: texture crunchiness  
- temp_hot: typically served hot (1.0) or cold (0.0)

**CRITICAL RULES:**
1. Return ONLY significant taste characteristics (values ≥ 0.6)
2. Most items should have 2-4 dominant axes, NOT all 10
3. DO NOT use 0.5 or neutral values
4. Omit axes that are not defining characteristics
5. Return ONLY valid JSON, no explanation

**Example profiles:**
```json
{"sweet": 0.9, "fattiness": 0.7, "temp_hot": 0.9}
```
(Chocolate crepe: sweet, rich, warm)

```json
{"umami": 0.9, "salty": 0.8, "fattiness": 0.85, "temp_hot": 1.0}
```  
(Cheese and ham waffle: savory, salty, rich, hot)

```json
{"sweet": 0.7, "sour": 0.8} 
```
(Lemonade: sweet and tart, room temp beverage)

```json
{"umami": 0.95, "spicy": 0.9, "temp_hot": 1.0}
```
(Curry chicken: intensely savory, very spicy, hot)"""


def generate_llm_taste_profile(
    item_name: Optional[str],
    item_description: Optional[str] = None,
    ingredients: Optional[List[str]] = None
) -> Dict[str, float]:
    """Generate realistic taste profile using OpenAI LLM.
    
    Returns:
        Dict with only significant taste axes (values >= 0.6),
        or empty dict if generation fails.
    """
    
    if not item_name:
        return {}
    
    # Build context string
    context_parts = [f"Menu Item: {item_name}"]
    
    if item_description and item_description.strip():
        context_parts.append(f"Description: {item_description}")
    
    if ingredients and len(ingredients) > 0:
        ingredients_str = ", ".join(ingredients[:10])  # Limit to first 10
        context_parts.append(f"Ingredients: {ingredients_str}")
    
    context_text = "\n".join(context_parts)
    
    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": TASTE_PROFILE_SYSTEM_PROMPT},
                {"role": "user", "content": context_text}
            ],
            temperature=0.2,  # Low temperature for consistency
            max_completion_tokens=300
        )
        
        content = response.choices[0].message.content.strip()
        
        # Extract JSON from code blocks if present
        if "```" in content:
            parts = content.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    content = part
                    break
        
        # Parse JSON
        profile = json.loads(content)
        
        # Validate and filter
        validated_profile = {}
        valid_axes = {"sweet", "sour", "salty", "bitter", "umami", "spicy", "fattiness", "acidity", "crunch", "temp_hot"}
        
        for axis, value in profile.items():
            if axis not in valid_axes:
                continue
            
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            
            # Clamp to [0, 1]
            value = max(0.0, min(1.0, value))
            
            # Only keep significant values
            if value >= 0.6 or value <= 0.4:
                validated_profile[axis] = round(value, 3)
        
        return validated_profile
        
    except Exception as e:
        # Silent fail - caller will use keyword fallback
        return {}
