from uuid import uuid4
from sqlmodel import Session
from config.database import engine, create_db_and_tables
from models import User, Restaurant, MenuItem
from services.features import has_allergen, build_item_features
from services.onboarding_service import OnboardingService
from services.recommendation_service import RecommendationService


def setup_module():
    create_db_and_tables()


def test_allergen_filter_explicit_and_derived():
    assert has_allergen(["peanut"], ["peanut"], [])
    assert has_allergen(["gluten"], ["dough"], [])  # derived from ingredient meta
    assert has_allergen(["lactose"], [], ["lactose"])  # explicit


def test_onboarding_early_stop():
    with Session(engine) as s:
        u = User()
        s.add(u); s.commit(); s.refresh(u)
        svc = OnboardingService()
        q = svc.start(u, s)
        # answer up to max to trigger completion via early-stop or cap
        res = {}
        for _ in range(6):
            res = svc.answer(u, q.get("question_id", ""), "B", s)
            if res.get("complete"):
                break
    assert res.get("complete")


def test_build_item_features():
    f = build_item_features(["tomato", "mozzarella"], ["cheesy", "baked"])
    assert isinstance(f, dict) and f


def test_allergy_filtering():
    with Session(engine) as s:
        r = Restaurant(name="Test R")
        s.add(r); s.commit(); s.refresh(r)
        safe = MenuItem(restaurant_id=r.id, name="Tomato Salad", ingredients=["tomato"], allergens=[], dietary_tags=["vegan"], cuisine=["Mediterranean"], features=build_item_features(["tomato"], []), provenance={"source":"ingested"}, inference_confidence=1.0)
        unsafe = MenuItem(restaurant_id=r.id, name="Peanut Noodles", ingredients=["peanut"], allergens=["peanut"], dietary_tags=[], cuisine=["Chinese"], features=build_item_features(["peanut"], []), provenance={"source":"ingested"}, inference_confidence=1.0)
        s.add(safe); s.add(unsafe); s.commit()
        u = User(); u.allergies = ["peanut"]; s.add(u); s.commit(); s.refresh(u)
        rec = RecommendationService()
        out = rec.recommend(s, u, str(r.id), 10)
        names = [i["name"] for i in out["items"]]
        assert "Peanut Noodles" not in names and "Tomato Salad" in names
