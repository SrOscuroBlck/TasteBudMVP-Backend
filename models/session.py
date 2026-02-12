from __future__ import annotations
from typing import List, Optional, Dict
from datetime import datetime
from uuid import uuid4, UUID
from enum import Enum
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON


class MealIntent(str, Enum):
    APPETIZER = "appetizer"
    MAIN_COURSE = "main_course"
    DESSERT = "dessert"
    FULL_MEAL = "full_meal"
    SNACK = "snack"
    BEVERAGE = "beverage"


class FeedbackType(str, Enum):
    LIKE = "like"
    DISLIKE = "dislike"
    SAVE_FOR_LATER = "save_for_later"
    SELECTED = "selected"


class RecommendationSession(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True)
    restaurant_id: UUID = Field(index=True)
    
    meal_intent: str
    hunger_level: str = "moderate"
    
    time_of_day: str
    detected_hour: int
    day_of_week: int
    budget: Optional[float] = None
    party_size: int = 1
    time_constraint_minutes: Optional[int] = None
    mood: Optional[str] = None
    occasion: Optional[str] = None
    dietary_notes: Optional[str] = None
    
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    selected_items: List[UUID] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "active"
    
    items_shown: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    excluded_items: List[UUID] = Field(default_factory=list, sa_column=Column(JSON))
    iteration_count: int = 0
    
    user_experience_level: str = "learning"
    context_snapshot: Dict = Field(default_factory=dict, sa_column=Column(JSON))
    
    email_scheduled_at: Optional[datetime] = None
    email_sent_at: Optional[datetime] = None


class RecommendationFeedback(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    session_id: UUID = Field(index=True)
    item_id: UUID = Field(index=True)
    
    feedback_type: str
    comment: Optional[str] = None
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PostMealFeedback(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    session_id: UUID = Field(index=True)
    
    items_ordered: List[UUID] = Field(sa_column=Column(JSON))
    
    overall_satisfaction: int
    would_order_again: bool
    taste_match: int
    
    portion_size_rating: Optional[int] = None
    value_for_money: Optional[int] = None
    service_quality: Optional[int] = None
    wait_time_minutes: Optional[int] = None
    
    additional_notes: Optional[str] = None
    
    submitted_at: datetime = Field(default_factory=datetime.utcnow)


class UserOrderHistory(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True)
    restaurant_id: UUID = Field(index=True)
    item_id: UUID = Field(index=True)
    
    ordered_at: datetime = Field(default_factory=datetime.utcnow)
    session_id: Optional[UUID] = None
    was_recommended: bool = False
    
    enjoyed: Optional[bool] = None
    rating: Optional[int] = None
    repeat_count: int = 1
