import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select
from config.database import engine
from models import MenuItem
from services.features import build_item_features


def populate_missing_features():
    with Session(engine) as session:
        items = session.exec(select(MenuItem)).all()
        
        updated_count = 0
        for item in items:
            if not item.features or len(item.features) == 0:
                features = build_item_features(item.ingredients, item.dietary_tags)
                
                if not features or len(features) == 0:
                    features = generate_default_features(item)
                
                item.features = features
                updated_count += 1
                print(f"Updated {item.name}: {len(features)} features")
        
        session.commit()
        print(f"\nUpdated {updated_count} items with features")


def generate_default_features(item: MenuItem) -> dict:
    defaults = {
        "sweet": 0.5,
        "sour": 0.5,
        "salty": 0.5,
        "bitter": 0.5,
        "umami": 0.5,
        "spicy": 0.5,
        "fattiness": 0.5,
        "acidity": 0.5,
        "crunch": 0.5,
        "temp_hot": 0.5
    }
    
    keyword_to_features = {
        "egg": {"umami": 0.7, "fattiness": 0.6},
        "huevo": {"umami": 0.7, "fattiness": 0.6},
        "waffle": {"sweet": 0.6, "fattiness": 0.5},
        "crepe": {"sweet": 0.6, "fattiness": 0.4},
        "fruit": {"sweet": 0.8, "acidity": 0.6},
        "fruta": {"sweet": 0.8, "acidity": 0.6},
        "cheese": {"fattiness": 0.7, "umami": 0.6, "salty": 0.6},
        "queso": {"fattiness": 0.7, "umami": 0.6, "salty": 0.6},
        "bacon": {"fattiness": 0.8, "salty": 0.8, "umami": 0.7},
        "tocineta": {"fattiness": 0.8, "salty": 0.8, "umami": 0.7},
        "syrup": {"sweet": 0.9},
        "miel": {"sweet": 0.9},
        "butter": {"fattiness": 0.9},
        "mantequilla": {"fattiness": 0.9},
    }
    
    name_lower = item.name.lower()
    desc_lower = (item.description or "").lower()
    combined_text = f"{name_lower} {desc_lower}"
    
    for keyword, adjustments in keyword_to_features.items():
        if keyword in combined_text:
            for axis, value in adjustments.items():
                defaults[axis] = min(1.0, (defaults[axis] + value) / 2)
    
    return defaults


if __name__ == "__main__":
    populate_missing_features()
