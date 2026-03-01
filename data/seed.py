from uuid import uuid4
from pathlib import Path
import sys

# Ensure project root is on sys.path so `from models import ...` works whether this
# script is run inside the container or from the repository root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session
from models import Restaurant, MenuItem, PopulationStats, User
from config.database import engine, create_db_and_tables
from services.features import build_item_features
from utils.logger import setup_logger

logger = setup_logger(__name__)


def seed():
    create_db_and_tables()
    with Session(engine) as s:
        r1 = Restaurant(id=uuid4(), name="Pasta Place", location="Downtown", tags=["Italian"])
        r2 = Restaurant(id=uuid4(), name="Spice Hub", location="Market St", tags=["Mexican"])
        s.add(r1); s.add(r2)

        items = [
            {"restaurant_id": r1.id, "name": "Margherita Pizza", "ingredients": ["dough","tomato","mozzarella"], "dietary_tags": ["vegetarian"], "cuisine": ["Italian"], "price": 12.5, "tags": ["cheesy","baked"]},
            {"restaurant_id": r1.id, "name": "Beef Lasagna", "ingredients": ["beef","dough","mozzarella"], "dietary_tags": [], "cuisine": ["Italian"], "price": 14.0, "tags": ["cheesy","baked"]},
            {"restaurant_id": r2.id, "name": "Spicy Beef Taco", "ingredients": ["beef","chili"], "dietary_tags": [], "cuisine": ["Mexican"], "price": 4.5, "tags": ["spicy","fried"]},
            {"restaurant_id": r2.id, "name": "Tofu Bowl", "ingredients": ["tofu","tomato"], "dietary_tags": ["vegan"], "cuisine": ["Mexican"], "price": 9.0, "tags": ["hot"]},
        ]
        for it in items:
            feats = build_item_features(it["ingredients"], it.get("tags", []))
            s.add(MenuItem(restaurant_id=it["restaurant_id"], name=it["name"], description="", ingredients=it["ingredients"], allergens=[], dietary_tags=it.get("dietary_tags", []), cuisine=it.get("cuisine", []), price=it.get("price"), features=feats, provenance={"source": "ingested"}, inference_confidence=1.0))

        pop = PopulationStats(
            axis_prior_mean={"sweet":0.4,"sour":0.4,"salty":0.5,"bitter":0.3,"umami":0.6,"fatty":0.5,"spicy":0.3},
            axis_prior_sigma={k:0.5 for k in ["sweet","sour","salty","bitter","umami","fatty","spicy"]},
            cuisine_prior={"Italian":0.6,"Mexican":0.5},
            item_popularity_global={},
            item_popularity_by_restaurant={},
            decay_half_life_days=30,
        )
        s.add(pop)

        s.commit()
        logger.info("Database seeded successfully", extra={"restaurants": 2, "menu_items": 4})


if __name__ == "__main__":
    seed()
