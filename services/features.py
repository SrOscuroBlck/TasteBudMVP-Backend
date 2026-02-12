from __future__ import annotations
from typing import Dict, List, Optional
import math


CANON_INGREDIENTS: Dict[str, Dict] = {
    # ingredient: meta
    "tomato": {"allergen": None, "axes": {"acidity": 0.6, "umami": 0.2}},
    "mozzarella": {"allergen": "lactose", "axes": {"fattiness": 0.7, "umami": 0.3}},
    "basil": {"allergen": None, "axes": {"acidity": 0.1}},
    "dough": {"allergen": "gluten", "axes": {"sweet": 0.1}},
    "beef": {"allergen": None, "axes": {"umami": 0.7, "fattiness": 0.5}},
    "chili": {"allergen": None, "axes": {"spicy": 0.9, "acidity": 0.2}},
    "peanut": {"allergen": "peanut", "axes": {"fattiness": 0.6}},
    "shrimp": {"allergen": "shellfish", "axes": {"umami": 0.6}},
    "tofu": {"allergen": None, "axes": {"umami": 0.3}},
}

CUISINES = ["Italian", "Mexican", "Japanese", "Chinese", "Indian", "American", "Mediterranean"]


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def cosine_similarity(a: Dict[str, float], b: Dict[str, float]) -> float:
    keys = set(a.keys()) | set(b.keys())
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    na = math.sqrt(sum((a.get(k, 0.0)) ** 2 for k in keys))
    nb = math.sqrt(sum((b.get(k, 0.0)) ** 2 for k in keys))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def canonicalize_ingredient(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def build_item_features(
    ingredients: List[str], 
    tags: List[str],
    item_name: Optional[str] = None,
    item_description: Optional[str] = None
) -> Dict[str, float]:
    axes: Dict[str, float] = {}
    for ing in ingredients:
        key = canonicalize_ingredient(ing)
        meta = CANON_INGREDIENTS.get(key)
        if not meta:
            continue
        for axis, val in meta.get("axes", {}).items():
            axes[axis] = axes.get(axis, 0.0) + val

    # tags influence
    tag_axis_map = {
        "fried": {"fattiness": 0.3, "umami": 0.1},
        "grilled": {"umami": 0.1},
        "spicy": {"spicy": 0.6},
        "cheesy": {"fattiness": 0.4, "umami": 0.2},
        "sweet": {"sweet": 0.6},
        "sour": {"sour": 0.6},
        "crunchy": {"crunch": 0.5},
        "hot": {"temp_hot": 0.7},
        "cold": {"temp_hot": -0.5},
    }

    for t in tags:
        if t in tag_axis_map:
            for axis, val in tag_axis_map[t].items():
                axes[axis] = axes.get(axis, 0.0) + val

    # normalize to [0,1]
    if axes:
        m = max(abs(v) for v in axes.values())
        if m > 0:
            axes = {k: clamp01((v / m + 1) / 2) for k, v in axes.items()}
    
    if not axes and (item_name or item_description or ingredients):
        axes = generate_fallback_features(ingredients, tags, item_name, item_description)
    
    return axes


def generate_fallback_features(
    ingredients: List[str],
    tags: List[str],
    item_name: Optional[str] = None,
    item_description: Optional[str] = None
) -> Dict[str, float]:
    """Generate taste profile using LLM or advanced keyword matching.
    
    Returns only SIGNIFICANT taste axes (values > 0.6 or < 0.4),
    not neutral 0.5 for everything.
    """
    
    # Try LLM-based generation first
    try:
        from .llm_features import generate_llm_taste_profile
        llm_profile = generate_llm_taste_profile(item_name, item_description, ingredients)
        if llm_profile and len(llm_profile) > 0:
            return llm_profile
    except Exception:
        pass  # Fall through to keyword matching
    
    # Enhanced keyword matching with weighted contribution
    profile_accumulator = {}
    
    keyword_to_features = {
        # Proteins
        "huevo": {"umami": 0.75, "fattiness": 0.7, "temp_hot": 1.0},
        "egg": {"umami": 0.75, "fattiness": 0.7, "temp_hot": 1.0},
        "pollo": {"umami": 0.8, "salty": 0.6, "temp_hot": 1.0},
        "chicken": {"umami": 0.8, "salty": 0.6, "temp_hot": 1.0},
        "carne": {"umami": 0.85, "salty": 0.7, "fattiness": 0.8},
        "beef": {"umami": 0.85, "salty": 0.7, "fattiness": 0.8},
        "cerdo": {"umami": 0.8, "fattiness": 0.8, "salty": 0.7},
        "pork": {"umami": 0.8, "fattiness": 0.8, "salty": 0.7},
        "jamón": {"salty": 0.8, "umami": 0.7, "fattiness": 0.6},
        "ham": {"salty": 0.8, "umami": 0.7, "fattiness": 0.6},
        "bacon": {"fattiness": 0.9, "salty": 0.9, "umami": 0.8},
        "tocineta": {"fattiness": 0.9, "salty": 0.9, "umami": 0.8},
        "salmon": {"fattiness": 0.7, "umami": 0.7, "temp_hot": 0.8},
        "camarones": {"umami": 0.8, "salty": 0.7, "temp_hot": 1.0},
        "shrimp": {"umami": 0.8, "salty": 0.7, "temp_hot": 1.0},
        "calamar": {"umami": 0.8, "salty": 0.6, "temp_hot": 1.0},
        "squid": {"umami": 0.8, "salty": 0.6, "temp_hot": 1.0},
        
        # Dairy
        "queso": {"fattiness": 0.8, "umami": 0.7, "salty": 0.7},
        "cheese": {"fattiness": 0.8, "umami": 0.7, "salty": 0.7},
        "crema": {"fattiness": 0.8, "sweet": 0.6},
        "cream": {"fattiness": 0.8, "sweet": 0.6},
        "mantequilla": {"fattiness": 0.95},
        "butter": {"fattiness": 0.95},
        
        # Sweet Items
        "waffle": {"sweet": 0.7, "fattiness": 0.6, "temp_hot": 0.9},
        "crepe": {"sweet": 0.65, "fattiness": 0.5, "temp_hot": 0.8},
        "pancake": {"sweet": 0.7, "fattiness": 0.6, "temp_hot": 0.9},
        "chocolate": {"sweet": 0.9, "bitter": 0.4, "fattiness": 0.7},
        "miel": {"sweet": 0.95},
        "honey": {"sweet": 0.95},
        "syrup": {"sweet": 0.95},
        "azúcar": {"sweet": 1.0},
        "sugar": {"sweet": 1.0},
        "helado": {"sweet": 0.8, "fattiness": 0.7},
        "ice cream": {"sweet": 0.8, "fattiness": 0.7},
        
        # Fruits & Veg
        "fruta": {"sweet": 0.7, "acidity": 0.5},
        "fruit": {"sweet": 0.7, "acidity": 0.5},
        "limón": {"sour": 0.9, "acidity": 0.9},
        "lemon": {"sour": 0.9, "acidity": 0.9},
        "naranja": {"sweet": 0.7, "sour": 0.5, "acidity": 0.6},
        "orange": {"sweet": 0.7, "sour": 0.5, "acidity": 0.6},
        "aguacate": {"fattiness": 0.8, "umami": 0.4},
        "avocado": {"fattiness": 0.8, "umami": 0.4},
        "tomate": {"umami": 0.5, "acidity": 0.7, "sour": 0.4},
        "tomato": {"umami": 0.5, "acidity": 0.7, "sour": 0.4},
        
        # Spices & Flavor
        "curry": {"spicy": 0.85, "umami": 0.7, "temp_hot": 1.0},
        "picante": {"spicy": 0.9},
        "spicy": {"spicy": 0.9},
        "ajo": {"umami": 0.6, "salty": 0.4},
        "garlic": {"umami": 0.6, "salty": 0.4},
        
        # Preparations
        "frito": {"fattiness": 0.8, "crunch": 0.7, "temp_hot": 1.0},
        "fried": {"fattiness": 0.8, "crunch": 0.7, "temp_hot": 1.0},
        "crispy": {"crunch": 0.9, "fattiness": 0.6},
        "crujiente": {"crunch": 0.9, "fattiness": 0.6},
    }
    
    # Combine all text
    combined_text = ""
    if item_name:
        combined_text += item_name.lower() + " "
    if item_description:
        combined_text += item_description.lower() + " "
    for ing in ingredients:
        combined_text += ing.lower() + " "
    for tag in tags:
        combined_text += tag.lower() + " "
    
    # Accumulate weighted contributions
    for keyword, adjustments in keyword_to_features.items():
        if keyword in combined_text:
            for axis, value in adjustments.items():
                if axis not in profile_accumulator:
                    profile_accumulator[axis] = []
                profile_accumulator[axis].append(value)
    
    # Average contributions and keep only significant values
    profile = {}
    for axis, values in profile_accumulator.items():
        avg = sum(values) / len(values)
        # Only include significant taste characteristics
        if avg >= 0.6:  # Strong positive characteristic
            profile[axis] = min(1.0, avg)
    
    # If no matches, provide minimal sensible defaults based on course
    if not profile:
        # Analyze item name for basic classification
        name_lower = (item_name or "").lower()
        
        if any(word in name_lower for word in ["limonada", "jugo", "batido", "bebida"]):
            # Beverages - simple sweet profile
            profile = {"sweet": 0.6}
        elif any(word in name_lower for word in ["ensalada", "salad"]):
            # Salads - fresh and light
            profile = {"acidity": 0.6, "crunch": 0.7}
        elif any(word in name_lower for word in ["sopa", "soup"]):
            # Soups - hot and savory
            profile = {"umami": 0.6, "temp_hot": 1.0}
        else:
            # Default savory profile for unknown items
            profile = {"umami": 0.6, "salty": 0.6}
    
    return profile


def violates_diet(dietary_rules: List[str], item_tags: List[str]) -> bool:
    rules = set(map(str.lower, dietary_rules))
    tags = set(map(str.lower, item_tags))
    if "vegan" in rules and "vegan" not in tags:
        return True
    if "vegetarian" in rules and not ("vegetarian" in tags or "vegan" in tags):
        return True
    # basic placeholders for halal/kosher when tagged explicitly
    if "halal" in rules and "halal" not in tags:
        return True
    if "kosher" in rules and "kosher" not in tags:
        return True
    return False


def has_allergen(allergies: List[str], ingredients: List[str], explicit_allergens: Optional[List[str]] = None) -> bool:
    alls = set(map(str.lower, allergies))
    if explicit_allergens:
        if any(a.lower() in alls for a in explicit_allergens):
            return True
    for ing in ingredients:
        key = canonicalize_ingredient(ing)
        meta = CANON_INGREDIENTS.get(key)
        if meta and meta.get("allergen") and meta["allergen"].lower() in alls:
            return True
    return False
