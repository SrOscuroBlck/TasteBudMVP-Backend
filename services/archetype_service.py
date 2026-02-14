from __future__ import annotations
from typing import Optional, List, Dict
from uuid import UUID
from sqlmodel import Session, select

from models.population import TasteArchetype
from models.user import TASTE_AXES


class ArchetypeNotFoundError(Exception):
    pass


def get_archetype_by_id(session: Session, archetype_id: UUID) -> TasteArchetype:
    archetype = session.get(TasteArchetype, archetype_id)
    
    if not archetype:
        raise ArchetypeNotFoundError(f"Archetype {archetype_id} not found")
    
    return archetype


def get_all_archetypes(session: Session) -> List[TasteArchetype]:
    archetypes = session.exec(select(TasteArchetype)).all()
    return list(archetypes)


def find_closest_archetype(session: Session, user_preferences: Dict[str, any]) -> TasteArchetype:
    archetypes = get_all_archetypes(session)
    
    if not archetypes:
        return create_default_archetype()
    
    best_archetype = archetypes[0]
    best_score = 0.0
    
    for archetype in archetypes:
        score = calculate_preference_match_score(archetype, user_preferences)
        if score > best_score:
            best_score = score
            best_archetype = archetype
    
    return best_archetype


def calculate_preference_match_score(archetype: TasteArchetype, preferences: Dict[str, any]) -> float:
    score = 0.0
    weight_sum = 0.0
    
    spice_preference = preferences.get("spice_level", 3)
    if spice_preference is not None:
        spice_match = calculate_spice_match(archetype, spice_preference)
        score += spice_match * 0.4
        weight_sum += 0.4
    
    sweet_vs_savory = preferences.get("sweet_vs_savory")
    if sweet_vs_savory:
        flavor_match = calculate_flavor_preference_match(archetype, sweet_vs_savory)
        score += flavor_match * 0.3
        weight_sum += 0.3
    
    cuisine_preference = preferences.get("preferred_cuisine")
    if cuisine_preference:
        cuisine_match = calculate_cuisine_match(archetype, cuisine_preference)
        score += cuisine_match * 0.3
        weight_sum += 0.3
    
    if weight_sum > 0:
        return score / weight_sum
    
    return 0.5


def calculate_spice_match(archetype: TasteArchetype, spice_level: int) -> float:
    archetype_spice = archetype.taste_vector.get("spicy", 0.5)
    
    normalized_preference = (spice_level - 1) / 4.0
    
    distance = abs(archetype_spice - normalized_preference)
    
    return 1.0 - distance


def calculate_flavor_preference_match(archetype: TasteArchetype, preference: str) -> float:
    sweet_value = archetype.taste_vector.get("sweet", 0.5)
    umami_value = archetype.taste_vector.get("umami", 0.5)
    salty_value = archetype.taste_vector.get("salty", 0.5)
    
    savory_value = (umami_value + salty_value) / 2.0
    
    if preference == "sweet":
        return sweet_value
    elif preference == "savory":
        return savory_value
    else:
        balance = 1.0 - abs(sweet_value - savory_value)
        return balance


def calculate_cuisine_match(archetype: TasteArchetype, preferred_cuisine: str) -> float:
    if not archetype.typical_cuisines:
        return 0.5
    
    normalized_preference = preferred_cuisine.lower()
    normalized_typical = [c.lower() for c in archetype.typical_cuisines]
    
    if normalized_preference in normalized_typical:
        return 1.0
    
    return 0.3


def create_default_archetype() -> TasteArchetype:
    return TasteArchetype(
        name="Balanced Palate",
        description="Enjoys a wide variety of flavors with moderate intensity",
        taste_vector={axis: 0.5 for axis in TASTE_AXES},
        typical_cuisines=[],
        example_items=[]
    )


def initialize_user_from_archetype(archetype: TasteArchetype) -> Dict[str, float]:
    return archetype.taste_vector.copy()


def get_archetype_descriptions_for_onboarding(session: Session) -> List[Dict[str, any]]:
    archetypes = get_all_archetypes(session)
    
    return [
        {
            "id": str(archetype.id),
            "name": archetype.name,
            "description": archetype.description,
            "example_items": archetype.example_items[:2],
            "cuisines": archetype.typical_cuisines[:2]
        }
        for archetype in archetypes
    ]
