from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from sklearn.cluster import KMeans
from sqlmodel import Session, select
from collections import Counter
from uuid import UUID
from typing import List, Dict, Tuple

from config.database import engine
from models.restaurant import MenuItem
from models.population import TasteArchetype
from models.user import TASTE_AXES


class ArchetypeClusteringError(Exception):
    pass


ARCHETYPE_DESCRIPTIONS = {
    "comfort_food": "Enjoys rich, satisfying dishes with high fat content and savory flavors",
    "spice_adventurer": "Loves bold, spicy flavors and is not afraid of heat",
    "health_conscious": "Prefers lighter, fresher options with balanced nutrition",
    "sweet_lover": "Gravitates toward sweet flavors and desserts",
    "savory_explorer": "Seeks deep umami and salty flavors in complex dishes",
    "balanced_palate": "Appreciates variety and moderate intensity across all taste dimensions"
}


def cluster_taste_archetypes(n_clusters: int = 6, dry_run: bool = False) -> List[TasteArchetype]:
    print(f"CLUSTERING {n_clusters} TASTE ARCHETYPES FROM MENU ITEMS")
    
    with Session(engine) as session:
        items = session.exec(select(MenuItem)).all()
        
        if len(items) < n_clusters:
            raise ArchetypeClusteringError(
                f"Need at least {n_clusters} menu items, found {len(items)}"
            )
        
        print(f"\nCollecting taste vectors from {len(items)} items...")
        
        vectors, item_map = extract_taste_vectors(items)
        
        if len(vectors) < n_clusters:
            raise ArchetypeClusteringError(
                f"Only {len(vectors)} items have valid taste vectors, need {n_clusters}"
            )
        
        print(f"Running K-Means clustering with {n_clusters} clusters...")
        
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=20, max_iter=300)
        labels = kmeans.fit_predict(vectors)
        centroids = kmeans.cluster_centers_
        
        archetypes = []
        used_names = set()
        
        for cluster_idx in range(n_clusters):
            archetype = build_archetype(
                cluster_idx,
                centroids[cluster_idx],
                labels,
                item_map,
                used_names
            )
            
            archetypes.append(archetype)
            used_names.add(archetype.name)
            print_archetype_summary(archetype, cluster_idx, labels)
        
        if not dry_run:
            save_archetypes_to_database(session, archetypes)
        
        return archetypes


def extract_taste_vectors(items: List[MenuItem]) -> Tuple[np.ndarray, List[MenuItem]]:
    vectors = []
    valid_items = []
    
    for item in items:
        if not item.features:
            continue
        
        vector = build_vector_from_features(item.features)
        
        if len(vector) == len(TASTE_AXES):
            vectors.append(vector)
            valid_items.append(item)
    
    return (np.array(vectors), valid_items)


def build_vector_from_features(features: Dict[str, float]) -> List[float]:
    return [features.get(axis, 0.5) for axis in TASTE_AXES]


def build_archetype(
    cluster_idx: int,
    centroid: np.ndarray,
    labels: np.ndarray,
    item_map: List[MenuItem],
    used_names: set
) -> TasteArchetype:
    cluster_items = [item_map[i] for i in range(len(labels)) if labels[i] == cluster_idx]
    
    taste_vector = build_taste_vector_from_centroid(centroid)
    name, description = identify_archetype_name(taste_vector, cluster_idx, used_names)
    cuisines = extract_typical_cuisines(cluster_items)
    examples = extract_example_items(cluster_items)
    
    return TasteArchetype(
        name=name,
        description=description,
        taste_vector=taste_vector,
        typical_cuisines=cuisines,
        example_items=examples
    )


def build_taste_vector_from_centroid(centroid: np.ndarray) -> Dict[str, float]:
    return {
        axis: float(round(centroid[i], 3))
        for i, axis in enumerate(TASTE_AXES)
    }


def identify_archetype_name(taste_vector: Dict[str, float], cluster_idx: int, used_names: set) -> Tuple[str, str]:
    dominant_axes = sorted(
        taste_vector.items(),
        key=lambda x: x[1],
        reverse=True
    )[:2]
    
    base_name = None
    description = None
    
    if taste_vector.get("spicy", 0) >= 0.65:
        base_name = "Spice Adventurer"
        description = ARCHETYPE_DESCRIPTIONS["spice_adventurer"]
    
    elif taste_vector.get("sweet", 0) >= 0.65:
        base_name = "Sweet Lover"
        description = ARCHETYPE_DESCRIPTIONS["sweet_lover"]
    
    elif taste_vector.get("fatty", 0) >= 0.65:
        base_name = "Comfort Food Lover"
        description = ARCHETYPE_DESCRIPTIONS["comfort_food"]
    
    elif taste_vector.get("umami", 0) >= 0.60 and taste_vector.get("salty", 0) >= 0.55:
        base_name = "Savory Explorer"
        description = ARCHETYPE_DESCRIPTIONS["savory_explorer"]
    
    elif np.var(list(taste_vector.values())) < 0.02:
        base_name = "Balanced Palate"
        description = ARCHETYPE_DESCRIPTIONS["balanced_palate"]
    
    elif taste_vector.get("fatty", 0) < 0.45:
        base_name = "Health Conscious"
        description = ARCHETYPE_DESCRIPTIONS["health_conscious"]
    
    else:
        base_name = f"Archetype {cluster_idx + 1}"
        description = "Enjoys a unique combination of flavors"
    
    unique_name = make_name_unique(base_name, used_names)
    
    return (unique_name, description)


def make_name_unique(base_name: str, used_names: set) -> str:
    if base_name not in used_names:
        return base_name
    
    suffix = 2
    while f"{base_name} {suffix}" in used_names:
        suffix += 1
    
    return f"{base_name} {suffix}"


def extract_typical_cuisines(items: List[MenuItem]) -> List[str]:
    all_cuisines = []
    for item in items:
        if item.cuisine:
            all_cuisines.extend(item.cuisine)
    
    if not all_cuisines:
        return []
    
    cuisine_counts = Counter(all_cuisines)
    top_cuisines = [cuisine for cuisine, count in cuisine_counts.most_common(3)]
    
    return top_cuisines


def extract_example_items(items: List[MenuItem]) -> List[str]:
    if len(items) <= 3:
        return [item.name for item in items]
    
    return [item.name for item in items[:3]]


def save_archetypes_to_database(session: Session, archetypes: List[TasteArchetype]) -> None:
    existing = session.exec(select(TasteArchetype)).all()
    
    for archetype in existing:
        session.delete(archetype)
    
    session.commit()
    
    for archetype in archetypes:
        session.add(archetype)
    
    session.commit()
    
    print(f"\nSaved {len(archetypes)} archetypes to database")


def print_archetype_summary(archetype: TasteArchetype, idx: int, labels: np.ndarray) -> None:
    cluster_size = np.sum(labels == idx)
    print(f"\n--- {archetype.name} ---")
    print(f"Cluster size: {cluster_size} items")
    print(f"Description: {archetype.description}")
    print(f"Dominant tastes: {get_dominant_tastes(archetype.taste_vector)}")
    print(f"Typical cuisines: {', '.join(archetype.typical_cuisines) or 'None'}")
    print(f"Examples: {', '.join(archetype.example_items[:3])}")


def get_dominant_tastes(taste_vector: Dict[str, float]) -> str:
    dominant = [
        f"{axis}={value:.2f}"
        for axis, value in sorted(taste_vector.items(), key=lambda x: x[1], reverse=True)[:3]
        if value > 0.55
    ]
    return ", ".join(dominant) if dominant else "balanced"


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Cluster menu items into taste archetypes"
    )
    parser.add_argument(
        "--clusters",
        type=int,
        default=6,
        help="Number of archetypes to create (default: 6)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show clusters without saving to database"
    )
    
    args = parser.parse_args()
    
    try:
        archetypes = cluster_taste_archetypes(n_clusters=args.clusters, dry_run=args.dry_run)
        
        print("\n" + "="*60)
        print(f"CREATED {len(archetypes)} TASTE ARCHETYPES")
        print("="*60)
        
        if args.dry_run:
            print("\nDRY RUN - No changes saved to database")
        else:
            print("\nArchetypes saved successfully!")
            print("\nNext steps:")
            print("1. Update onboarding flow to present archetype choices")
            print("2. New users will be initialized with archetype centroids")
    
    except ArchetypeClusteringError as e:
        print(f"\nError: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
