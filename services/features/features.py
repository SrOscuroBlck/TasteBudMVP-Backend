from __future__ import annotations
from typing import Dict, List, Optional
import math


CANON_INGREDIENTS: Dict[str, Dict] = {
    "tomato": {"allergen": None, "axes": {"sour": 0.6, "umami": 0.2}},
    "mozzarella": {"allergen": "lactose", "axes": {"fatty": 0.7, "umami": 0.3}},
    "basil": {"allergen": None, "axes": {"sour": 0.1}},
    "dough": {"allergen": "gluten", "axes": {"sweet": 0.1}},
    "beef": {"allergen": None, "axes": {"umami": 0.7, "fatty": 0.5}},
    "chili": {"allergen": None, "axes": {"spicy": 0.9, "sour": 0.2}},
    "peanut": {"allergen": "peanut", "axes": {"fatty": 0.6}},
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
    item_description: Optional[str] = None,
    cached_llm_profile: Optional[Dict[str, float]] = None
) -> Dict[str, float]:
    if cached_llm_profile:
        return cached_llm_profile
    
    llm_profile = generate_llm_taste_profile_with_fallback(
        item_name,
        item_description,
        ingredients
    )
    
    if llm_profile:
        return llm_profile
    
    return generate_keyword_based_features(ingredients, tags, item_name, item_description)


def generate_llm_taste_profile_with_fallback(
    item_name: Optional[str],
    item_description: Optional[str],
    ingredients: List[str]
) -> Dict[str, float]:
    try:
        from .llm_features import generate_llm_taste_profile
        taste, texture, richness = generate_llm_taste_profile(item_name, item_description, ingredients)
        if taste and len(taste) > 0:
            return taste
    except Exception:
        pass
    
    return {}


def generate_keyword_based_features(
    ingredients: List[str],
    tags: List[str],
    item_name: Optional[str] = None,
    item_description: Optional[str] = None
) -> Dict[str, float]:
    axes = build_axes_from_ingredients(ingredients)
    axes = apply_tag_modifiers(axes, tags)
    
    if axes:
        axes = normalize_axes(axes)
        return axes
    
    return generate_keyword_matching_profile(ingredients, tags, item_name, item_description)


def build_axes_from_ingredients(ingredients: List[str]) -> Dict[str, float]:
    axes: Dict[str, float] = {}
    
    for ing in ingredients:
        key = canonicalize_ingredient(ing)
        meta = CANON_INGREDIENTS.get(key)
        if not meta:
            continue
        for axis, val in meta.get("axes", {}).items():
            axes[axis] = axes.get(axis, 0.0) + val
    
    return axes


def apply_tag_modifiers(axes: Dict[str, float], tags: List[str]) -> Dict[str, float]:
    tag_axis_map = {
        "fried": {"fatty": 0.3, "umami": 0.1},
        "grilled": {"umami": 0.1},
        "spicy": {"spicy": 0.6},
        "cheesy": {"fatty": 0.4, "umami": 0.2},
        "sweet": {"sweet": 0.6},
        "sour": {"sour": 0.6},
        "crunchy": {"fatty": 0.2},
        "hot": {"spicy": 0.4},
        "cold": {},
    }

    for t in tags:
        if t in tag_axis_map:
            for axis, val in tag_axis_map[t].items():
                axes[axis] = axes.get(axis, 0.0) + val
    
    return axes


def normalize_axes(axes: Dict[str, float]) -> Dict[str, float]:
    m = max(abs(v) for v in axes.values())
    if m > 0:
        return {k: clamp01((v / m + 1) / 2) for k, v in axes.items()}
    return axes


def generate_keyword_matching_profile(
    ingredients: List[str],
    tags: List[str],
    item_name: Optional[str],
    item_description: Optional[str]
) -> Dict[str, float]:
    profile_accumulator = {}
    
    keyword_to_features = {
        # Proteins
        "huevo": {"umami": 0.75, "fatty": 0.7},
        "egg": {"umami": 0.75, "fatty": 0.7},
        "pollo": {"umami": 0.8, "salty": 0.6},
        "chicken": {"umami": 0.8, "salty": 0.6},
        "carne": {"umami": 0.85, "salty": 0.7, "fatty": 0.8},
        "beef": {"umami": 0.85, "salty": 0.7, "fatty": 0.8},
        "cerdo": {"umami": 0.8, "fatty": 0.8, "salty": 0.7},
        "pork": {"umami": 0.8, "fatty": 0.8, "salty": 0.7},
        "jamón": {"salty": 0.8, "umami": 0.7, "fatty": 0.6},
        "ham": {"salty": 0.8, "umami": 0.7, "fatty": 0.6},
        "bacon": {"fatty": 0.9, "salty": 0.9, "umami": 0.8},
        "tocineta": {"fatty": 0.9, "salty": 0.9, "umami": 0.8},
        "salmon": {"fatty": 0.7, "umami": 0.7},
        "camarones": {"umami": 0.8, "salty": 0.7},
        "shrimp": {"umami": 0.8, "salty": 0.7},
        "calamar": {"umami": 0.8, "salty": 0.6},
        "squid": {"umami": 0.8, "salty": 0.6},
        
        # Dairy
        "queso": {"fatty": 0.8, "umami": 0.7, "salty": 0.7},
        "cheese": {"fatty": 0.8, "umami": 0.7, "salty": 0.7},
        "crema": {"fatty": 0.8, "sweet": 0.6},
        "cream": {"fatty": 0.8, "sweet": 0.6},
        "mantequilla": {"fatty": 0.95},
        "butter": {"fatty": 0.95},
        
        # Sweet Items
        "waffle": {"sweet": 0.7, "fatty": 0.6},
        "crepe": {"sweet": 0.65, "fatty": 0.5},
        "pancake": {"sweet": 0.7, "fatty": 0.6},
        "chocolate": {"sweet": 0.9, "bitter": 0.4, "fatty": 0.7},
        "miel": {"sweet": 0.95},
        "honey": {"sweet": 0.95},
        "syrup": {"sweet": 0.95},
        "azúcar": {"sweet": 1.0},
        "sugar": {"sweet": 1.0},
        "helado": {"sweet": 0.8, "fatty": 0.7},
        "ice cream": {"sweet": 0.8, "fatty": 0.7},
        
        # Fruits & Veg
        "fruta": {"sweet": 0.7, "sour": 0.5},
        "fruit": {"sweet": 0.7, "sour": 0.5},
        "limón": {"sour": 0.9},
        "lemon": {"sour": 0.9},
        "naranja": {"sweet": 0.7, "sour": 0.6},
        "orange": {"sweet": 0.7, "sour": 0.6},
        "aguacate": {"fatty": 0.8, "umami": 0.4},
        "avocado": {"fatty": 0.8, "umami": 0.4},
        "tomate": {"umami": 0.5, "sour": 0.6},
        "tomato": {"umami": 0.5, "sour": 0.6},
        
        # Spices & Flavor
        "curry": {"spicy": 0.85, "umami": 0.7},
        "picante": {"spicy": 0.9},
        "spicy": {"spicy": 0.9},
        "ajo": {"umami": 0.6, "salty": 0.4},
        "garlic": {"umami": 0.6, "salty": 0.4},
        
        # Preparations
        "frito": {"fatty": 0.8, "umami": 0.6},
        "fried": {"fatty": 0.8, "umami": 0.6},
        "crispy": {"fatty": 0.6, "umami": 0.5},
        "crujiente": {"fatty": 0.6, "umami": 0.5},
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
    
    if not profile:
        name_lower = (item_name or "").lower()
        
        if any(word in name_lower for word in ["limonada", "jugo", "batido", "bebida"]):
            profile = {"sweet": 0.6}
        elif any(word in name_lower for word in ["ensalada", "salad"]):
            profile = {"sour": 0.6, "bitter": 0.4}
        elif any(word in name_lower for word in ["sopa", "soup"]):
            profile = {"umami": 0.6, "salty": 0.5}
        else:
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
