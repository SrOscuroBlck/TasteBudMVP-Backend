#!/usr/bin/env python3
"""
Smart feature regeneration for Crepes & Waffles menu items.

Uses LLM to generate realistic taste profiles based on item names and descriptions,
replacing the generic 0.5 neutral values that prevent personalization.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlmodel import Session, select
from config.database import engine
from models import MenuItem
from uuid import UUID
from openai import OpenAI
from config.settings import settings
import json

RESTAURANT_ID = UUID("b62a20c0-3742-4083-b8f7-ebaf91bf0b12")  # Crepes & Waffles

client = OpenAI(api_key=settings.OPENAI_API_KEY)


TASTE_PROFILE_PROMPT = """You are a culinary expert analyzing menu items to generate taste profiles.

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

**IMPORTANT RULES:**
1. NOT ALL AXES NEED VALUES - only set axes that are SIGNIFICANT (>0.6 or defining characteristics)
2. Most items should have 2-4 dominant axes, not all 10
3. Use 0.5 ONLY when truly neutral, prefer omitting minor axes
4. Beverages should have simple profiles (sweet, sour, temp_hot)
5. Savory dishes focus on: umami, salty, fattiness, temp_hot
6. Desserts focus on: sweet, fattiness, temp_hot

Return ONLY a JSON object with the taste profile, no explanation.

Example responses:
{"sweet": 0.8, "fattiness": 0.7, "temp_hot": 1.0}  # Chocolate crepe
{"umami": 0.8, "salty": 0.7, "fattiness": 0.9, "temp_hot": 1.0}  # Cheese waffle
{"sweet": 0.7, "sour": 0.6}  # Lemonade (cold beverage, sweet and sour)
{"umami": 0.9, "spicy": 0.8, "temp_hot": 1.0}  # Curry dish"""


def generate_taste_profile_with_llm(item_name: str, item_description: str = "") -> dict:
    """Use LLM to generate realistic taste profile for menu item."""
    
    if item_description and item_description.strip():
        item_text = f"{item_name}\nDescription: {item_description}"
    else:
        item_text = item_name
    
    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": TASTE_PROFILE_PROMPT},
                {"role": "user", "content": f"Generate taste profile for:\n{item_text}"}
            ],
            temperature=0.3,
            max_completion_tokens=300
        )
        
        content = response.choices[0].message.content.strip()
        
        # Try to extract JSON if wrapped in code blocks
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        
        profile = json.loads(content)
        
        # Validate and cap values
        validated_profile = {}
        all_axes = ["sweet", "sour", "salty", "bitter", "umami", "spicy", "fattiness", "acidity", "crunch", "temp_hot"]
        
        for axis in all_axes:
            if axis in profile:
                value = float(profile[axis])
                value = max(0.0, min(1.0, value))
                if value >= 0.3:  # Only keep significant values
                    validated_profile[axis] = value
        
        # If profile is empty or all neutral, return simple fallback based on name
        if not validated_profile or all(0.4 <= v <= 0.6 for v in validated_profile.values()):
            return generate_simple_fallback(item_name)
        
        return validated_profile
        
    except Exception as e:
        print(f"❌ LLM generation failed for '{item_name}': {e}")
        return generate_simple_fallback(item_name)


def generate_simple_fallback(item_name: str) -> dict:
    """Generate simple taste profile based on keywords in item name."""
    name_lower = item_name.lower()
    profile = {}
    
    # Beverages
    if any(kw in name_lower for kw in ["limonada", "jugo", "batido", "bebida", "cerveza"]):
        profile["sweet"] = 0.6
        if "limonada" in name_lower:
            profile["sour"] = 0.7
        return profile
    
    # Desserts/Sweet items
    if any(kw in name_lower for kw in ["waffle", "crepe", "dulce", "chocolate", "helado", "miel"]):
        profile["sweet"] = 0.7
        profile["fattiness"] = 0.6
        profile["temp_hot"] = 0.8
    
    # Savory dishes
    if any(kw in name_lower for kw in ["pollo", "carne", "res", "cerdo", "huev"]):
        profile["umami"] = 0.7
        profile["salty"] = 0.6
        profile["fattiness"] = 0.7
        profile["temp_hot"] = 1.0
    
    # Seafood
    if any(kw in name_lower for kw in ["calamar", "camaron", "pescado", "salmon"]):
        profile["umami"] = 0.8
        profile["salty"] = 0.7
        profile["temp_hot"] = 1.0
    
    # Spicy indicators
    if any(kw in name_lower for kw in ["curry", "picante", "spicy"]):
        profile["spicy"] = 0.8
    
    # Cheese-heavy
    if any(kw in name_lower for kw in ["queso", "cheese", "parmesano"]):
        profile["fattiness"] = 0.8
        profile["umami"] = 0.7
        profile["salty"] = 0.6
    
    return profile if profile else {"sweet": 0.5, "umami": 0.5}


def regenerate_features():
    """Regenerate features for all Crepes & Waffles items with neutral profiles."""
    
    with Session(engine) as session:
        # Find items with neutral features (all values around 0.5)
        items = session.exec(
            select(MenuItem).where(MenuItem.restaurant_id == RESTAURANT_ID)
        ).all()
        
        neutral_items = []
        for item in items:
            if not item.features or len(item.features) == 0:
                neutral_items.append(item)
            elif all(0.4 <= v <= 0.6 for v in item.features.values()):
                neutral_items.append(item)
        
        print(f"📊 Found {len(neutral_items)} items with neutral features out of {len(items)} total")
        print()
        
        if len(neutral_items) == 0:
            print("✅ No neutral items found, all items already have features")
            return
        
        print("🤖 Generating realistic taste profiles using LLM...")
        print()
        
        updated_count = 0
        skipped_count = 0
        
        for i, item in enumerate(neutral_items, 1):
            print(f"[{i}/{len(neutral_items)}] {item.name}")
            
            # Generate new profile
            new_profile = generate_taste_profile_with_llm(item.name, item.description)
            
            # Show the generated profile
            profile_str = ", ".join(f"{k}:{v:.2f}" for k, v in sorted(new_profile.items()))
            print(f"  → {profile_str}")
            
            # Update database
            item.features = new_profile
            session.add(item)
            updated_count += 1
            
            # Commit every 10 items
            if i % 10 == 0:
                session.commit()
                print(f"  ✅ Committed {i} items")
                print()
        
        # Final commit
        session.commit()
        
        print()
        print("="*80)
        print(f"✅ Feature regeneration complete!")
        print(f"   Updated: {updated_count} items")
        print(f"   Skipped: {skipped_count} items")
        print("="*80)
        print()
        print("🔄 Next steps:")
        print("   1. Regenerate embeddings: docker exec tastebud_api python scripts/generate_embeddings.py")
        print("   2. Rebuild FAISS index: docker exec tastebud_api python scripts/build_faiss_index.py 1536")
        print("   3. Restart API: docker-compose restart api")


if __name__ == "__main__":
    regenerate_features()
