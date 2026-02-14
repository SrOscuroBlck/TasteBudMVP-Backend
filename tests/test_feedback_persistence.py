"""
Integration test for feedback persistence across sessions

This is the CRITICAL test that validates the main bug fix:
"Items marked as DISLIKE in one session should NOT appear in future sessions"
"""

from uuid import uuid4, UUID
from datetime import datetime, timedelta
from sqlmodel import Session, select
from config.database import engine, create_db_and_tables
from models import User, Restaurant, MenuItem
from models.session import RecommendationSession, RecommendationFeedback, FeedbackType
from services.unified_feedback_service import UnifiedFeedbackService
from services.recommendation_service import RecommendationService
from services.features import build_item_features


def setup_module():
    create_db_and_tables()


def create_test_user_with_profile(session: Session) -> User:
    user = User(
        email=f"integration_test_{uuid4()}@test.com",
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
        permanently_excluded_items=[],
        allergies=[],
        dietary_rules=[]
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def create_test_restaurant_with_menu(session: Session, item_count: int = 10) -> tuple[Restaurant, list[MenuItem]]:
    restaurant = Restaurant(name=f"Integration Test Restaurant {uuid4()}")
    session.add(restaurant)
    session.commit()
    session.refresh(restaurant)
    
    items = []
    for i in range(item_count):
        item = MenuItem(
            restaurant_id=restaurant.id,
            name=f"Test Item {i}",
            description=f"Description for item {i}",
            price=10.0 + i,
            ingredients=["ingredient1", "ingredient2"],
            allergens=[],
            dietary_tags=["vegetarian"],
            cuisine=["Italian"],
            features=build_item_features(["ingredient1", "ingredient2"], ["fresh"]),
            provenance={"source": "test"},
            inference_confidence=1.0
        )
        session.add(item)
        items.append(item)
    
    session.commit()
    for item in items:
        session.refresh(item)
    
    return restaurant, items


def test_disliked_item_excluded_from_next_session():
    """
    CRITICAL TEST: Verify disliked item does not appear in next session
    
    This is the main bug we're fixing:
    1. User gets recommendations in session 1
    2. User marks item as DISLIKE
    3. User starts session 2 at same restaurant
    4. Disliked item should NOT appear in recommendations
    """
    with Session(engine) as session:
        user = create_test_user_with_profile(session)
        restaurant, menu_items = create_test_restaurant_with_menu(session, item_count=15)
        
        rec_service = RecommendationService()
        feedback_service = UnifiedFeedbackService()
        
        session1 = RecommendationSession(
            user_id=user.id,
            restaurant_id=restaurant.id,
            meal_intent="main_course",
            time_of_day="dinner",
            detected_hour=19,
            day_of_week=3,
            status="active"
        )
        session.add(session1)
        session.commit()
        session.refresh(session1)
        
        disliked_item = menu_items[0]
        
        feedback_service.record_session_feedback(
            db_session=session,
            user=user,
            item=disliked_item,
            feedback_type=FeedbackType.DISLIKE,
            session_id=session1.id
        )
        
        session1.status = "completed"
        session1.completed_at = datetime.utcnow()
        session.add(session1)
        session.commit()
        
        session2 = RecommendationSession(
            user_id=user.id,
            restaurant_id=restaurant.id,
            meal_intent="main_course",
            time_of_day="dinner",
            detected_hour=19,
            day_of_week=4,
            status="active"
        )
        session.add(session2)
        session.commit()
        session.refresh(session2)
        session.refresh(user)
        
        recommendations = rec_service.recommend_for_session(
            session=session,
            user=user,
            restaurant_id=str(restaurant.id),
            recommendation_session=session2,
            count=10
        )
        
        recommended_ids = [item["id"] for item in recommendations["items"]]
        
        assert str(disliked_item.id) not in recommended_ids, \
            "Disliked item must NOT appear in next session recommendations"


def test_multiple_dislikes_all_excluded():
    """Test that multiple disliked items are all excluded from future sessions"""
    with Session(engine) as session:
        user = create_test_user_with_profile(session)
        restaurant, menu_items = create_test_restaurant_with_menu(session, item_count=15)
        
        rec_service = RecommendationService()
        feedback_service = UnifiedFeedbackService()
        
        session1 = RecommendationSession(
            user_id=user.id,
            restaurant_id=restaurant.id,
            meal_intent="main_course",
            time_of_day="dinner",
            detected_hour=19,
            day_of_week=3,
            status="active"
        )
        session.add(session1)
        session.commit()
        session.refresh(session1)
        
        disliked_items = menu_items[0:3]
        
        for item in disliked_items:
            feedback_service.record_session_feedback(
                db_session=session,
                user=user,
                item=item,
                feedback_type=FeedbackType.DISLIKE,
                session_id=session1.id
            )
        
        session1.status = "completed"
        session1.completed_at = datetime.utcnow()
        session.add(session1)
        session.commit()
        
        session2 = RecommendationSession(
            user_id=user.id,
            restaurant_id=restaurant.id,
            meal_intent="main_course",
            time_of_day="dinner",
            detected_hour=19,
            day_of_week=4,
            status="active"
        )
        session.add(session2)
        session.commit()
        session.refresh(session2)
        session.refresh(user)
        
        recommendations = rec_service.recommend_for_session(
            session=session,
            user=user,
            restaurant_id=str(restaurant.id),
            recommendation_session=session2,
            count=10
        )
        
        recommended_ids = [item["id"] for item in recommendations["items"]]
        disliked_ids = [str(item.id) for item in disliked_items]
        
        for disliked_id in disliked_ids:
            assert disliked_id not in recommended_ids, \
                f"Disliked item {disliked_id} must NOT appear in recommendations"


def test_dislike_persists_across_multiple_sessions():
    """Test that dislike persists even after multiple new sessions"""
    with Session(engine) as session:
        user = create_test_user_with_profile(session)
        restaurant, menu_items = create_test_restaurant_with_menu(session, item_count=15)
        
        rec_service = RecommendationService()
        feedback_service = UnifiedFeedbackService()
        
        session1 = RecommendationSession(
            user_id=user.id,
            restaurant_id=restaurant.id,
            meal_intent="main_course",
            time_of_day="dinner",
            detected_hour=19,
            day_of_week=1,
            status="completed",
            completed_at=datetime.utcnow()
        )
        session.add(session1)
        session.commit()
        session.refresh(session1)
        
        disliked_item = menu_items[0]
        feedback_service.record_session_feedback(
            db_session=session,
            user=user,
            item=disliked_item,
            feedback_type=FeedbackType.DISLIKE,
            session_id=session1.id
        )
        
        for day in range(2, 5):
            session_n = RecommendationSession(
                user_id=user.id,
                restaurant_id=restaurant.id,
                meal_intent="main_course",
                time_of_day="dinner",
                detected_hour=19,
                day_of_week=day,
                status="active"
            )
            session.add(session_n)
            session.commit()
            session.refresh(session_n)
            session.refresh(user)
            
            recommendations = rec_service.recommend_for_session(
                session=session,
                user=user,
                restaurant_id=str(restaurant.id),
                recommendation_session=session_n,
                count=10
            )
            
            recommended_ids = [item["id"] for item in recommendations["items"]]
            
            assert str(disliked_item.id) not in recommended_ids, \
                f"Disliked item must remain excluded in session {day}"
            
            session_n.status = "completed"
            session_n.completed_at = datetime.utcnow()
            session.add(session_n)
            session.commit()


def test_dislike_exclusion_window():
    """Test that dislike exclusion respects the 30-day window"""
    with Session(engine) as session:
        user = create_test_user_with_profile(session)
        restaurant, menu_items = create_test_restaurant_with_menu(session, item_count=15)
        
        feedback_service = UnifiedFeedbackService()
        
        old_session = RecommendationSession(
            user_id=user.id,
            restaurant_id=restaurant.id,
            meal_intent="main_course",
            time_of_day="dinner",
            detected_hour=19,
            day_of_week=1,
            started_at=datetime.utcnow() - timedelta(days=35),
            status="completed",
            completed_at=datetime.utcnow() - timedelta(days=35)
        )
        session.add(old_session)
        session.commit()
        session.refresh(old_session)
        
        old_disliked_item = menu_items[0]
        
        old_feedback = RecommendationFeedback(
            session_id=old_session.id,
            item_id=old_disliked_item.id,
            feedback_type="dislike",
            timestamp=datetime.utcnow() - timedelta(days=35)
        )
        session.add(old_feedback)
        session.commit()
        
        recent_session = RecommendationSession(
            user_id=user.id,
            restaurant_id=restaurant.id,
            meal_intent="main_course",
            time_of_day="dinner",
            detected_hour=19,
            day_of_week=2,
            status="completed",
            completed_at=datetime.utcnow() - timedelta(days=5)
        )
        session.add(recent_session)
        session.commit()
        session.refresh(recent_session)
        
        recent_disliked_item = menu_items[1]
        feedback_service.record_session_feedback(
            db_session=session,
            user=user,
            item=recent_disliked_item,
            feedback_type=FeedbackType.DISLIKE,
            session_id=recent_session.id
        )
        
        rec_service = RecommendationService()
        new_session = RecommendationSession(
            user_id=user.id,
            restaurant_id=restaurant.id,
            meal_intent="main_course",
            time_of_day="dinner",
            detected_hour=19,
            day_of_week=3,
            status="active"
        )
        session.add(new_session)
        session.commit()
        session.refresh(new_session)
        session.refresh(user)
        
        recommendations = rec_service.recommend_for_session(
            session=session,
            user=user,
            restaurant_id=str(restaurant.id),
            recommendation_session=new_session,
            count=10
        )
        
        recommended_ids = [item["id"] for item in recommendations["items"]]
        
        assert str(recent_disliked_item.id) not in recommended_ids, \
            "Recent dislike (5 days old) should still be excluded"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
