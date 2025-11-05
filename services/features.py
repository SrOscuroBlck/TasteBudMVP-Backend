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


def build_item_features(ingredients: List[str], tags: List[str]) -> Dict[str, float]:
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
    return axes


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
