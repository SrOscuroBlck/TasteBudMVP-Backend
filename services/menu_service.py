from __future__ import annotations
from typing import Dict, Any, List
from uuid import UUID, uuid4
from sqlmodel import Session
from models import MenuItem
from .features import build_item_features, canonicalize_ingredient
from .gpt_helper import infer_ingredients


class MenuService:
    def ingest(self, session: Session, restaurant_id: UUID, raw_items: List[Dict[str, Any]]) -> List[MenuItem]:
        upserted: List[MenuItem] = []
        for raw in raw_items:
            ingredients = [canonicalize_ingredient(i) for i in raw.get("ingredients", [])]
            tags = [t.lower() for t in raw.get("tags", [])]
            item = MenuItem(
                restaurant_id=restaurant_id,
                name=raw.get("name", "Unnamed"),
                description=raw.get("description", ""),
                ingredients=ingredients,
                allergens=raw.get("allergens", []),
                dietary_tags=raw.get("dietary_tags", []),
                cuisine=raw.get("cuisine", []),
                price=raw.get("price"),
                spice_level=raw.get("spice_level"),
                cooking_method=raw.get("cooking_method"),
                course=raw.get("course"),
                features=build_item_features(ingredients, tags),
                provenance={"source": "ingested"},
                inference_confidence=1.0,
            )
            session.add(item)
            upserted.append(item)
        session.commit()
        return upserted

    def infer_item(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        context = {"name": payload.get("name"), "description": payload.get("description", "")}
        data = infer_ingredients(context)
        if not data:
            return {"candidates": [], "tags": [], "axis_hints": {}, "confidence": 0.3}
        # canonicalize and compute confidence
        cands = [{"ingredient": canonicalize_ingredient(c["ingredient"]), "confidence": float(c.get("confidence", 0))} for c in data.get("candidates", [])]
        tags = [t.lower() for t in data.get("tags", [])]
        axis_hints = {k: float(v) for k, v in data.get("axis_hints", {}).items()}
        conf = sum(ci["confidence"] for ci in cands) / max(1, len(cands)) if cands else 0.5
        return {"candidates": cands, "tags": tags, "axis_hints": axis_hints, "confidence": conf}
