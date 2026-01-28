from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request
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
from services.gpt_helper import explain_similarity
from utils.logger import setup_logger

logger = setup_logger(__name__)

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
        user = User(id=body.user_id)
        session.add(user)
        session.commit()
        session.refresh(user)
        logger.info("Created new user", extra={"user_id": str(body.user_id)})
    
    logger.info("Starting onboarding", extra={"user_id": str(body.user_id)})
    svc = OnboardingService()
    return svc.start(user, session)


@router.post("/onboarding/answer")
def onboarding_answer(payload: Dict[str, Any], session: Session = Depends(get_session)):
    try:
        user_id = UUID(payload["user_id"])  # type: ignore[arg-type]
        user = session.get(User, user_id)
        if not user:
            logger.warning("User not found for onboarding answer", extra={"user_id": str(user_id)})
            raise HTTPException(404, "user not found")
        
        logger.info("Processing onboarding answer", extra={"user_id": str(user_id), "question_id": payload.get("question_id")})
        svc = OnboardingService()
        return svc.answer(user, payload["question_id"], payload["chosen_option_id"], session)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing onboarding answer", extra={"error": str(e)}, exc_info=True)
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
    logger.info("Ingesting menu items", extra={"restaurant_id": str(restaurant_id), "item_count": len(items)})
    svc = MenuService()
    up = svc.ingest(session, restaurant_id, items)
    logger.info("Menu ingestion complete", extra={"restaurant_id": str(restaurant_id), "ingested_count": len(up)})
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


@router.get("/restaurants")
def list_restaurants(session: Session = Depends(get_session)):
    """Return a list of restaurants (id, name, location, tags)."""
    rows = session.exec(select(Restaurant)).all()
    return [{"id": str(r.id), "name": r.name, "location": r.location, "tags": r.tags} for r in rows]


@router.get("/recommendations")
def recommendations(
    user_id: UUID,
    restaurant_id: Optional[UUID] = None,
    top_n: int = 10,
    budget: Optional[float] = None,
    time_of_day: Optional[str] = None,
    mood: Optional[str] = None,
    occasion: Optional[str] = None,
    session: Session = Depends(get_session)
):
    user = session.get(User, user_id)
    if not user:
        logger.warning("User not found for recommendations", extra={"user_id": str(user_id)})
        raise HTTPException(404, "user not found")
    
    logger.info(
        "Generating recommendations",
        extra={
            "user_id": str(user_id),
            "restaurant_id": str(restaurant_id) if restaurant_id else None,
            "top_n": top_n,
            "mood": mood,
            "occasion": occasion
        }
    )
    svc = RecommendationService()
    result = svc.recommend(
        session,
        user,
        str(restaurant_id) if restaurant_id else None,
        top_n,
        budget,
        time_of_day,
        mood,
        occasion
    )
    logger.info(
        "Recommendations generated",
        extra={
            "user_id": str(user_id),
            "result_count": len(result.get("items", [])) if isinstance(result, dict) else 0
        }
    )
    return result


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
    user_id = _UUID(payload["user_id"])
    user = session.get(User, user_id)
    if not user:
        logger.warning("User not found for feedback rating", extra={"user_id": str(user_id)})
        raise HTTPException(404, "user not found")
    
    logger.info("Recording feedback rating", extra={"user_id": str(user_id), "item_id": payload.get("item_id"), "rating": payload.get("rating")})
    svc = FeedbackService()
    r = svc.add_rating(session, user, payload["item_id"], int(payload["rating"]), bool(payload["liked"]), payload.get("reasons", []), payload.get("comment", ""))
    logger.info("Feedback rating recorded", extra={"user_id": str(user_id), "rating_id": str(r.id)})
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


@router.get("/items/{item_id}/similar")
def get_similar_items(
    item_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
    k: int = 10,
    cuisine: Optional[str] = None,
    max_price: Optional[float] = None,
    dietary: Optional[str] = None,
    explain: bool = False
):
    if not request.app.state.faiss_service:
        raise HTTPException(
            status_code=503,
            detail="FAISS index not available. Run scripts/build_faiss_index.py to build the index."
        )
    
    item = session.get(MenuItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="item not found")
    
    if item.reduced_embedding is None and item.embedding is None:
        raise HTTPException(
            status_code=400,
            detail="item has no embedding. Run scripts/generate_embeddings.py to generate embeddings."
        )
    
    query_embedding = item.reduced_embedding if item.reduced_embedding is not None else item.embedding
    
    if query_embedding is None:
        raise HTTPException(status_code=400, detail="item embedding is None")
    
    faiss_service = request.app.state.faiss_service
    
    candidate_k = k * 3
    similar_results = faiss_service.search(query_embedding, k=candidate_k)
    
    similar_item_ids = [result[0] for result in similar_results if result[0] != item_id]
    
    similar_items_query = select(MenuItem).where(MenuItem.id.in_(similar_item_ids))
    similar_items_db = session.exec(similar_items_query).all()
    
    items_map = {item.id: item for item in similar_items_db}
    scores_map = {result[0]: result[1] for result in similar_results}
    
    filtered_items = []
    for similar_id in similar_item_ids:
        similar_item = items_map.get(similar_id)
        if not similar_item:
            continue
        
        if cuisine and cuisine not in similar_item.cuisine:
            continue
        
        if max_price is not None and similar_item.price is not None and similar_item.price > max_price:
            continue
        
        if dietary:
            if dietary not in similar_item.dietary_tags:
                continue
        
        filtered_items.append({
            "item": similar_item,
            "score": scores_map.get(similar_id, 0.0)
        })
    
    filtered_items = filtered_items[:k]
    
    result_items = []
    for item_data in filtered_items:
        similar_item = item_data["item"]
        item_result = {
            "id": str(similar_item.id),
            "name": similar_item.name,
            "description": similar_item.description,
            "price": similar_item.price,
            "cuisine": similar_item.cuisine,
            "dietary_tags": similar_item.dietary_tags,
            "similarity_score": round(item_data["score"], 4)
        }
        
        if explain and len(result_items) < 3:
            explanation = explain_similarity(
                original_item=item.name,
                similar_item=similar_item.name,
                cuisine=similar_item.cuisine,
                score=item_data["score"]
            )
            if explanation:
                item_result["explanation"] = explanation
        
        result_items.append(item_result)
    
    logger.info(
        "Similar items retrieved",
        extra={
            "item_id": str(item_id),
            "candidates": len(similar_results),
            "filtered": len(result_items),
            "filters_applied": {"cuisine": cuisine, "max_price": max_price, "dietary": dietary}
        }
    )
    
    return {
        "item_id": str(item_id),
        "item_name": item.name,
        "similar_items": result_items,
        "metadata": {
            "total_candidates": len(similar_results),
            "filtered_count": len(result_items),
            "filters_applied": {
                "cuisine": cuisine,
                "max_price": max_price,
                "dietary": dietary
            }
        }
    }


@router.get("/items/{item_id}")
def get_item_details(item_id: UUID, session: Session = Depends(get_session)):
    item = session.get(MenuItem, item_id)
    if not item:
        logger.warning("Item not found", extra={"item_id": str(item_id)})
        raise HTTPException(404, "item not found")
    
    restaurant = session.get(Restaurant, item.restaurant_id)
    
    logger.info("Item details retrieved", extra={"item_id": str(item_id)})
    
    return {
        "id": str(item.id),
        "restaurant_id": str(item.restaurant_id),
        "restaurant_name": restaurant.name if restaurant else None,
        "name": item.name,
        "description": item.description,
        "ingredients": item.ingredients,
        "allergens": item.allergens,
        "dietary_tags": item.dietary_tags,
        "cuisine": item.cuisine,
        "price": item.price,
        "spice_level": item.spice_level,
        "cooking_method": item.cooking_method,
        "course": item.course,
        "features": item.features,
        "provenance": item.provenance,
        "inference_confidence": item.inference_confidence
    }


@router.get("/restaurants/{restaurant_id}")
def get_restaurant_details(restaurant_id: UUID, session: Session = Depends(get_session)):
    restaurant = session.get(Restaurant, restaurant_id)
    if not restaurant:
        logger.warning("Restaurant not found", extra={"restaurant_id": str(restaurant_id)})
        raise HTTPException(404, "restaurant not found")
    
    menu_items = session.exec(
        select(MenuItem).where(MenuItem.restaurant_id == restaurant_id)
    ).all()
    
    menu_count = len(menu_items)
    
    cuisines = set()
    price_range = {"min": None, "max": None}
    dietary_options = set()
    
    for item in menu_items:
        cuisines.update(item.cuisine)
        dietary_options.update(item.dietary_tags)
        
        if item.price is not None:
            if price_range["min"] is None or item.price < price_range["min"]:
                price_range["min"] = item.price
            if price_range["max"] is None or item.price > price_range["max"]:
                price_range["max"] = item.price
    
    logger.info(
        "Restaurant details retrieved",
        extra={"restaurant_id": str(restaurant_id), "menu_count": menu_count}
    )
    
    return {
        "id": str(restaurant.id),
        "name": restaurant.name,
        "location": restaurant.location,
        "tags": restaurant.tags,
        "menu_count": menu_count,
        "cuisines": sorted(list(cuisines)),
        "price_range": price_range,
        "dietary_options": sorted(list(dietary_options))
    }


@router.get("/search")
def search_items(
    q: Optional[str] = None,
    cuisine: Optional[str] = None,
    dietary: Optional[str] = None,
    max_price: Optional[float] = None,
    min_price: Optional[float] = None,
    restaurant_id: Optional[UUID] = None,
    limit: int = 50,
    session: Session = Depends(get_session)
):
    query = select(MenuItem)
    
    if restaurant_id:
        query = query.where(MenuItem.restaurant_id == restaurant_id)
    
    items = session.exec(query).all()
    
    filtered_items = []
    for item in items:
        if q and q.lower() not in item.name.lower() and q.lower() not in (item.description or "").lower():
            continue
        
        if cuisine and cuisine not in item.cuisine:
            continue
        
        if dietary and dietary not in item.dietary_tags:
            continue
        
        if max_price is not None and item.price is not None and item.price > max_price:
            continue
        
        if min_price is not None and item.price is not None and item.price < min_price:
            continue
        
        filtered_items.append(item)
    
    filtered_items = filtered_items[:limit]
    
    results = []
    for item in filtered_items:
        restaurant = session.get(Restaurant, item.restaurant_id)
        results.append({
            "id": str(item.id),
            "name": item.name,
            "description": item.description,
            "restaurant_id": str(item.restaurant_id),
            "restaurant_name": restaurant.name if restaurant else None,
            "cuisine": item.cuisine,
            "dietary_tags": item.dietary_tags,
            "price": item.price,
            "allergens": item.allergens
        })
    
    logger.info(
        "Search completed",
        extra={
            "query": q,
            "filters": {
                "cuisine": cuisine,
                "dietary": dietary,
                "price_range": f"{min_price}-{max_price}" if min_price or max_price else None
            },
            "result_count": len(results)
        }
    )
    
    return {
        "items": results,
        "count": len(results),
        "filters_applied": {
            "query": q,
            "cuisine": cuisine,
            "dietary": dietary,
            "max_price": max_price,
            "min_price": min_price,
            "restaurant_id": str(restaurant_id) if restaurant_id else None
        }
    }
