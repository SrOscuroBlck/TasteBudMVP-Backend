from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List, Optional
from uuid import UUID
from pydantic import BaseModel
from sqlmodel import Session, select
from config.database import get_session
from models import User, Restaurant, MenuItem
from services.onboarding_service import OnboardingService
from services.menu_service import MenuService
from services.recommendation_service import RecommendationService
from services.feedback_service import FeedbackService


router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


class OnboardingStartBody(BaseModel):
    user_id: UUID


@router.post("/onboarding/start")
def onboarding_start(body: OnboardingStartBody, session: Session = Depends(get_session)):
    user = session.get(User, body.user_id)
    if not user:
        user = User(id=body.user_id)  # create if new
        session.add(user)
        session.commit()
        session.refresh(user)
    svc = OnboardingService()
    return svc.start(user, session)


@router.post("/onboarding/answer")
def onboarding_answer(payload: Dict[str, Any], session: Session = Depends(get_session)):
    try:
        user_id = UUID(payload["user_id"])  # type: ignore[arg-type]
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(404, "user not found")
        svc = OnboardingService()
        return svc.answer(user, payload["question_id"], payload["chosen_option_id"], session)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/onboarding/state")
def onboarding_state(user_id: UUID, session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(404, "user not found")
    return user.onboarding_state or {}


 


@router.get("/users/{user_id}/profile")
def get_profile(user_id: UUID, session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(404, "user not found")
    return {
        "id": str(user.id),
        "allergies": user.allergies,
        "dietary_rules": user.dietary_rules,
        "liked_ingredients": user.liked_ingredients,
        "disliked_ingredients": user.disliked_ingredients,
        "taste_vector": user.taste_vector,
        "taste_uncertainty": user.taste_uncertainty,
        "cuisine_affinity": user.cuisine_affinity,
    }


@router.patch("/users/{user_id}/preferences")
def update_prefs(user_id: UUID, payload: Dict[str, Any], session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(404, "user not found")
    for k in ["allergies", "dietary_rules", "liked_ingredients", "disliked_ingredients"]:
        if k in payload:
            setattr(user, k, payload[k])
    session.add(user)
    session.commit()
    return {"status": "ok"}


@router.post("/restaurants/{restaurant_id}/menu/ingest")
def ingest_menu(restaurant_id: UUID, items: List[Dict[str, Any]], session: Session = Depends(get_session)):
    svc = MenuService()
    up = svc.ingest(session, restaurant_id, items)
    return {"count": len(up)}


@router.post("/restaurants/{restaurant_id}/menu/infer")
def infer_menu_item(restaurant_id: UUID, payload: Dict[str, Any]):
    svc = MenuService()
    return svc.infer_item(payload)


@router.get("/restaurants/{restaurant_id}/menu")
def list_menu(restaurant_id: UUID, session: Session = Depends(get_session)):
    items = session.exec(select(MenuItem).where(MenuItem.restaurant_id == restaurant_id)).all()
    return [{"id": str(i.id), "name": i.name, "price": i.price, "dietary_tags": i.dietary_tags} for i in items]


@router.post("/restaurants")
def create_restaurant(payload: Dict[str, Any], session: Session = Depends(get_session)):
    r = Restaurant(name=payload["name"], location=payload.get("location"), tags=payload.get("tags", []))
    session.add(r)
    session.commit()
    session.refresh(r)
    return {"id": str(r.id), "name": r.name}


@router.get("/recommendations")
def recommendations(user_id: UUID, restaurant_id: Optional[UUID] = None, top_n: int = 10, budget: Optional[float] = None, time_of_day: Optional[str] = None, session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(404, "user not found")
    svc = RecommendationService()
    return svc.recommend(session, user, str(restaurant_id) if restaurant_id else None, top_n, budget, time_of_day)


@router.post("/discovery/quick-like")
def quick_like(payload: Dict[str, Any], session: Session = Depends(get_session)):
    from uuid import UUID as _UUID
    user = session.get(User, _UUID(payload["user_id"]))
    if not user:
        raise HTTPException(404, "user not found")
    # Use feedback learning without storing a rating; treat as low-weight like/dislike
    svc = FeedbackService()
    # Reuse rating with minimal side effects
    liked = bool(payload.get("liked", True))
    item_id = payload["item_id"]
    svc.add_rating(session, user, item_id, 5 if liked else 1, liked, reasons=["quick_like"])  # learning effect
    return {"status": "ok"}

@router.post("/feedback/rating")
def post_rating(payload: Dict[str, Any], session: Session = Depends(get_session)):
    from uuid import UUID as _UUID
    user = session.get(User, _UUID(payload["user_id"]))
    if not user:
        raise HTTPException(404, "user not found")
    svc = FeedbackService()
    r = svc.add_rating(session, user, payload["item_id"], int(payload["rating"]), bool(payload["liked"]), payload.get("reasons", []), payload.get("comment", ""))
    return {"id": str(r.id)}


@router.post("/feedback/interaction")
def post_interaction(payload: Dict[str, Any], session: Session = Depends(get_session)):
    from uuid import UUID as _UUID
    user = session.get(User, _UUID(payload["user_id"]))
    if not user:
        raise HTTPException(404, "user not found")
    svc = FeedbackService()
    inter = svc.add_interaction(session, user, payload["item_id"], payload["type"])
    return {"id": str(inter.id)}
