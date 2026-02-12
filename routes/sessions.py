from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel
from sqlmodel import Session
from datetime import datetime
from config.database import get_session
from models import User
from models.session import MealIntent, FeedbackType
from services.session_service import RecommendationSessionService
from services.recommendation_service import RecommendationService
from services.unified_feedback_service import UnifiedFeedbackService
from routes.api import get_current_user
from utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/sessions", tags=["recommendation-sessions"])


class StartSessionRequest(BaseModel):
    restaurant_id: UUID
    meal_intent: MealIntent
    budget: Optional[float] = None
    time_constraint_minutes: Optional[int] = None


class VisitContext(BaseModel):
    is_repeat_visit: bool
    previous_visit_count: int
    last_visit_date: Optional[datetime]
    previous_orders: List[PreviousOrderSummary]


class StartSessionResponse(BaseModel):
    session_id: UUID
    message: str
    visit_context: Optional[VisitContext] = None


class NextRecommendationsRequest(BaseModel):
    count: int = 10


class RecommendationFeedbackRequest(BaseModel):
    item_id: UUID
    feedback_type: FeedbackType
    comment: Optional[str] = None


class CompleteSessionRequest(BaseModel):
    selected_item_ids: List[UUID]


class PreviousOrderSummary(BaseModel):
    item_id: str
    name: str
    times_ordered: int
    last_ordered: Optional[datetime]
    rating: Optional[int]


class SessionSummary(BaseModel):
    session_id: str
    date: datetime
    items_ordered: List[str]


class RestaurantVisitHistory(BaseModel):
    is_repeat_visit: bool
    previous_visit_count: int
    last_visit_date: Optional[datetime]
    favorite_items: List[PreviousOrderSummary]
    recent_sessions: List[SessionSummary]


@router.post("/start", response_model=StartSessionResponse)
def start_session(
    request: StartSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    if not request.restaurant_id:
        raise HTTPException(status_code=400, detail="restaurant_id is required to start session")
    
    if not request.meal_intent:
        raise HTTPException(status_code=400, detail="meal_intent is required to start session")
    
    session_service = RecommendationSessionService()
    
    visit_history = session_service.get_restaurant_visit_history(
        db_session=db,
        user_id=current_user.id,
        restaurant_id=request.restaurant_id
    )
    
    session_id = session_service.start_session(
        db_session=db,
        user_id=current_user.id,
        restaurant_id=request.restaurant_id,
        meal_intent=request.meal_intent.value,
        budget=request.budget,
        time_constraint_minutes=request.time_constraint_minutes
    )
    
    visit_context = None
    if visit_history["is_repeat_visit"]:
        visit_context = VisitContext(
            is_repeat_visit=visit_history["is_repeat_visit"],
            previous_visit_count=visit_history["previous_visit_count"],
            last_visit_date=visit_history["last_visit_date"],
            previous_orders=[
                PreviousOrderSummary(**item) for item in visit_history["favorite_items"]
            ]
        )
        
        message = f"Welcome back! You've visited this restaurant {visit_history['previous_visit_count']} time(s) before."
    else:
        message = "Welcome! This is your first visit to this restaurant. Let's find something great for you."
    
    logger.info(
        "Recommendation session started",
        extra={
            "user_id": str(current_user.id),
            "session_id": str(session_id),
            "is_repeat_visit": visit_history["is_repeat_visit"],
            "restaurant_id": str(request.restaurant_id),
            "meal_intent": request.meal_intent.value
        }
    )
    
    return StartSessionResponse(
        session_id=session_id,
        message=message,
        visit_context=visit_context
    )


@router.get("/{session_id}")
def get_session_details(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    session_service = RecommendationSessionService()
    rec_session = session_service.get_session(db, session_id)
    
    if not rec_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if rec_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot access other user's session")
    
    return {
        "id": str(rec_session.id),
        "user_id": str(rec_session.user_id),
        "restaurant_id": str(rec_session.restaurant_id),
        "meal_intent": rec_session.meal_intent,
        "budget": rec_session.budget,
        "time_constraint_minutes": rec_session.time_constraint_minutes,
        "status": rec_session.status,
        "started_at": rec_session.started_at.isoformat(),
        "completed_at": rec_session.completed_at.isoformat() if rec_session.completed_at else None,
        "items_shown": rec_session.items_shown,
        "excluded_items": rec_session.excluded_items,
        "context_snapshot": rec_session.context_snapshot
    }


@router.post("/{session_id}/next")
def get_next_recommendations(
    session_id: UUID,
    request: NextRecommendationsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    if request.count < 1 or request.count > 50:
        raise HTTPException(status_code=400, detail="count must be between 1 and 50")
    
    from models.session import RecommendationSession
    from sqlmodel import select
    
    statement = select(RecommendationSession).where(RecommendationSession.id == session_id)
    rec_session = db.exec(statement).first()
    
    if not rec_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if rec_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot access other user's session")
    
    if rec_session.status != "active":
        raise HTTPException(status_code=400, detail="Session is not active")
    
    recommendation_service = RecommendationService()
    
    try:
        results = recommendation_service.recommend_with_session(
            session=db,
            user=current_user,
            recommendation_session=rec_session,
            top_n=request.count
        )
        
        logger.info(
            "Next recommendations generated",
            extra={
                "user_id": str(current_user.id),
                "session_id": str(session_id),
                "count": len(results.get("items", []))
            }
        )
        
        return results
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            "Error generating next recommendations",
            extra={"error": str(e), "session_id": str(session_id)},
            exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{session_id}/feedback")
def add_feedback(
    session_id: UUID,
    request: RecommendationFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    if not request.item_id:
        raise HTTPException(status_code=400, detail="item_id is required for feedback")
    
    if not request.feedback_type:
        raise HTTPException(status_code=400, detail="feedback_type is required")
    
    session_service = RecommendationSessionService()
    rec_session = session_service.get_session(db, session_id)
    
    if not rec_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if rec_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot access other user's session")
    
    if rec_session.status != "active":
        raise HTTPException(status_code=400, detail="Session is not active")
    
    from models import MenuItem
    item = db.get(MenuItem, request.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    unified_feedback_service = UnifiedFeedbackService()
    feedback = unified_feedback_service.record_session_feedback(
        db_session=db,
        user=current_user,
        item=item,
        feedback_type=request.feedback_type,
        session_id=session_id,
        comment=request.comment
    )
    
    if request.feedback_type == FeedbackType.DISLIKE:
        session_service.add_excluded_item(db, session_id, request.item_id)
    
    logger.info(
        "Feedback recorded and profile updated",
        extra={
            "user_id": str(current_user.id),
            "session_id": str(session_id),
            "item_id": str(request.item_id),
            "feedback_type": request.feedback_type.value
        }
    )
    
    return {"success": True, "message": "Feedback recorded and profile updated"}


@router.post("/{session_id}/complete")
def complete_session(
    session_id: UUID,
    request: CompleteSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    if not request.selected_item_ids or len(request.selected_item_ids) == 0:
        raise HTTPException(status_code=400, detail="selected_item_ids list cannot be empty")
    
    session_service = RecommendationSessionService()
    rec_session = session_service.get_session(db, session_id)
    
    if not rec_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if rec_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot access other user's session")
    
    if rec_session.status != "active":
        raise HTTPException(status_code=400, detail="Session is not active")
    
    session_service.complete_session(
        db_session=db,
        session_id=session_id,
        selected_item_ids=request.selected_item_ids
    )
    
    logger.info(
        "Session completed",
        extra={
            "user_id": str(current_user.id),
            "session_id": str(session_id),
            "selected_items": [str(id) for id in request.selected_item_ids]
        }
    )
    
    return {
        "success": True,
        "message": "Session completed. You'll receive an email in 1 hour for post-meal feedback."
    }


@router.post("/{session_id}/abandon")
def abandon_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    session_service = RecommendationSessionService()
    rec_session = session_service.get_session(db, session_id)
    
    if not rec_session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if rec_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot access other user's session")
    
    if rec_session.status != "active":
        raise HTTPException(status_code=400, detail="Session is not active")
    
    session_service.abandon_session(db, session_id)
    
    logger.info(
        "Session abandoned",
        extra={
            "user_id": str(current_user.id),
            "session_id": str(session_id)
        }
    )
    
    return {"success": True, "message": "Session abandoned"}


@router.get("/restaurant/{restaurant_id}/history", response_model=RestaurantVisitHistory)
def get_restaurant_visit_history(
    restaurant_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
):
    """
    Get user's visit history at a specific restaurant.
    Returns previous sessions, orders, and favorite items.
    """
    if not restaurant_id:
        raise HTTPException(status_code=400, detail="restaurant_id is required")
    
    session_service = RecommendationSessionService()
    
    history = session_service.get_restaurant_visit_history(
        db_session=db,
        user_id=current_user.id,
        restaurant_id=restaurant_id
    )
    
    logger.info(
        "Restaurant visit history retrieved",
        extra={
            "user_id": str(current_user.id),
            "restaurant_id": str(restaurant_id),
            "is_repeat_visit": history["is_repeat_visit"]
        }
    )
    
    return history
