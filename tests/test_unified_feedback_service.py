"""
Unit tests for UnifiedFeedbackService

Tests the critical feedback persistence and profile update logic.
"""

from uuid import uuid4, UUID
from datetime import datetime
from sqlmodel import Session
from config.database import engine, create_db_and_tables
from models import User, Restaurant, MenuItem
from models.session import RecommendationSession, RecommendationFeedback, FeedbackType
from services.unified_feedback_service import UnifiedFeedbackService
from services.features import build_item_features


def setup_module():
    create_db_and_tables()


def create_test_user(session: Session) -> User:
    user = User(
        email=f"test_{uuid4()}@test.com",
        hashed_password="test",
        taste_vector={
            "sweet": 0.5,
            "salty": 0.5,
            "sour": 0.5,
            "bitter": 0.5,
            "umami": 0.5,
            "spicy": 0.5,
            "fatty": 0.5,
            "crunchy": 0.5,
            "fresh": 0.5,
            "complex": 0.5
        },
        cuisine_affinity={},
        permanently_excluded_items=[]
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def create_test_restaurant(session: Session) -> Restaurant:
    restaurant = Restaurant(name=f"Test Restaurant {uuid4()}")
    session.add(restaurant)
    session.commit()
    session.refresh(restaurant)
    return restaurant


def create_test_menu_item(session: Session, restaurant_id: UUID, spicy: float = 0.0, cuisine: str = "Italian") -> MenuItem:
    item = MenuItem(
        restaurant_id=restaurant_id,
        name=f"Test Item {uuid4()}",
        ingredients=["tomato", "basil"],
        allergens=[],
        dietary_tags=["vegetarian"],
        cuisine=[cuisine],
        features=build_item_features(["tomato", "basil"], ["fresh"]),
        provenance={"source": "test"},
        inference_confidence=1.0
    )
    
    if spicy > 0:
        item.features["taste"]["spicy"] = spicy
    
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def create_test_session(session: Session, user_id: UUID, restaurant_id: UUID) -> RecommendationSession:
    rec_session = RecommendationSession(
        user_id=user_id,
        restaurant_id=restaurant_id,
        meal_intent="main_course",
        time_of_day="dinner",
        detected_hour=19,
        day_of_week=3,
        status="active"
    )
    session.add(rec_session)
    session.commit()
    session.refresh(rec_session)
    return rec_session


def test_feedback_creates_database_record():
    """Test that feedback is properly saved to database"""
    with Session(engine) as session:
        user = create_test_user(session)
        restaurant = create_test_restaurant(session)
        menu_item = create_test_menu_item(session, restaurant.id)
        rec_session = create_test_session(session, user.id, restaurant.id)
        
        service = UnifiedFeedbackService()
        service.record_session_feedback(
            db_session=session,
            user=user,
            item=menu_item,
            feedback_type=FeedbackType.DISLIKE,
            session_id=rec_session.id
        )
        
        feedback = session.query(RecommendationFeedback).filter(
            RecommendationFeedback.session_id == rec_session.id,
            RecommendationFeedback.item_id == menu_item.id
        ).first()
        
        assert feedback is not None
        assert feedback.feedback_type == "dislike"


def test_dislike_updates_taste_vector():
    """Test that dislike feedback negatively adjusts taste preferences"""
    with Session(engine) as session:
        user = create_test_user(session)
        restaurant = create_test_restaurant(session)
        
        spicy_item = create_test_menu_item(session, restaurant.id, spicy=0.9)
        rec_session = create_test_session(session, user.id, restaurant.id)
        
        initial_spicy = user.taste_vector.get("spicy", 0.5)
        
        service = UnifiedFeedbackService()
        service.record_session_feedback(
            db_session=session,
            user=user,
            item=spicy_item,
            feedback_type=FeedbackType.DISLIKE,
            session_id=rec_session.id
        )
        
        session.refresh(user)
        final_spicy = user.taste_vector.get("spicy", 0.5)
        
        assert final_spicy < initial_spicy, "Spicy preference should decrease after disliking spicy item"


def test_like_updates_taste_vector():
    """Test that like feedback positively adjusts taste preferences"""
    with Session(engine) as session:
        user = create_test_user(session)
        restaurant = create_test_restaurant(session)
        
        spicy_item = create_test_menu_item(session, restaurant.id, spicy=0.9)
        rec_session = create_test_session(session, user.id, restaurant.id)
        
        initial_spicy = user.taste_vector.get("spicy", 0.5)
        
        service = UnifiedFeedbackService()
        service.record_session_feedback(
            db_session=session,
            user=user,
            item=spicy_item,
            feedback_type=FeedbackType.LIKE,
            session_id=rec_session.id
        )
        
        session.refresh(user)
        final_spicy = user.taste_vector.get("spicy", 0.5)
        
        assert final_spicy > initial_spicy, "Spicy preference should increase after liking spicy item"


def test_selected_updates_taste_vector_strongly():
    """Test that selected (ordered) feedback has stronger impact than like"""
    with Session(engine) as session:
        user1 = create_test_user(session)
        user2 = create_test_user(session)
        restaurant = create_test_restaurant(session)
        
        spicy_item1 = create_test_menu_item(session, restaurant.id, spicy=0.9)
        spicy_item2 = create_test_menu_item(session, restaurant.id, spicy=0.9)
        
        rec_session1 = create_test_session(session, user1.id, restaurant.id)
        rec_session2 = create_test_session(session, user2.id, restaurant.id)
        
        initial_spicy1 = user1.taste_vector.get("spicy", 0.5)
        initial_spicy2 = user2.taste_vector.get("spicy", 0.5)
        
        service = UnifiedFeedbackService()
        
        service.record_session_feedback(
            db_session=session,
            user=user1,
            item=spicy_item1,
            feedback_type=FeedbackType.LIKE,
            session_id=rec_session1.id
        )
        
        service.record_session_feedback(
            db_session=session,
            user=user2,
            item=spicy_item2,
            feedback_type=FeedbackType.SELECTED,
            session_id=rec_session2.id
        )
        
        session.refresh(user1)
        session.refresh(user2)
        
        delta_like = user1.taste_vector.get("spicy", 0.5) - initial_spicy1
        delta_selected = user2.taste_vector.get("spicy", 0.5) - initial_spicy2
        
        assert delta_selected > delta_like, "Selected should have stronger impact than like"


def test_dislike_updates_cuisine_affinity():
    """Test that disliking an item decreases affinity for its cuisine"""
    with Session(engine) as session:
        user = create_test_user(session)
        restaurant = create_test_restaurant(session)
        
        italian_item = create_test_menu_item(session, restaurant.id, cuisine="Italian")
        rec_session = create_test_session(session, user.id, restaurant.id)
        
        initial_italian_affinity = user.cuisine_affinity.get("Italian", 0.5)
        
        service = UnifiedFeedbackService()
        service.record_session_feedback(
            db_session=session,
            user=user,
            item=italian_item,
            feedback_type=FeedbackType.DISLIKE,
            session_id=rec_session.id
        )
        
        session.refresh(user)
        final_italian_affinity = user.cuisine_affinity.get("Italian", 0.5)
        
        assert final_italian_affinity < initial_italian_affinity, "Italian affinity should decrease"


def test_permanent_exclusion_not_added_for_regular_dislike():
    """Test that regular dislike does NOT add to permanent exclusions"""
    with Session(engine) as session:
        user = create_test_user(session)
        restaurant = create_test_restaurant(session)
        
        menu_item = create_test_menu_item(session, restaurant.id)
        rec_session = create_test_session(session, user.id, restaurant.id)
        
        service = UnifiedFeedbackService()
        service.record_session_feedback(
            db_session=session,
            user=user,
            item=menu_item,
            feedback_type=FeedbackType.DISLIKE,
            session_id=rec_session.id
        )
        
        session.refresh(user)
        
        assert len(user.permanently_excluded_items) == 0, "Regular dislike should not add permanent exclusion"


def test_feedback_updates_last_updated_timestamp():
    """Test that giving feedback updates user's last_updated timestamp"""
    with Session(engine) as session:
        user = create_test_user(session)
        restaurant = create_test_restaurant(session)
        menu_item = create_test_menu_item(session, restaurant.id)
        rec_session = create_test_session(session, user.id, restaurant.id)
        
        initial_timestamp = user.last_updated
        
        service = UnifiedFeedbackService()
        service.record_session_feedback(
            db_session=session,
            user=user,
            item=menu_item,
            feedback_type=FeedbackType.LIKE,
            session_id=rec_session.id
        )
        
        session.refresh(user)
        
        assert user.last_updated > initial_timestamp, "last_updated should be updated after feedback"


def test_multiple_dislikes_compound():
    """Test that multiple dislikes compound the taste vector adjustment"""
    with Session(engine) as session:
        user = create_test_user(session)
        restaurant = create_test_restaurant(session)
        rec_session = create_test_session(session, user.id, restaurant.id)
        
        initial_spicy = user.taste_vector.get("spicy", 0.5)
        
        service = UnifiedFeedbackService()
        
        for _ in range(3):
            spicy_item = create_test_menu_item(session, restaurant.id, spicy=0.9)
            service.record_session_feedback(
                db_session=session,
                user=user,
                item=spicy_item,
                feedback_type=FeedbackType.DISLIKE,
                session_id=rec_session.id
            )
            session.refresh(user)
        
        final_spicy = user.taste_vector.get("spicy", 0.5)
        
        assert final_spicy < initial_spicy - 0.1, "Three dislikes should significantly decrease preference"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
