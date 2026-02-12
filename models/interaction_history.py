"""
User Item Interaction History Model

Tracks every time a menu item is shown to a user, along with engagement outcomes.
This enables novelty scoring and helps prevent showing the same items repeatedly.
"""

from __future__ import annotations
from typing import List
from datetime import datetime
from uuid import uuid4, UUID
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON


class UserItemInteractionHistory(SQLModel, table=True):
    """
    Tracks every time an item is shown to a user across all sessions.
    Used for novelty scoring and avoiding repetitive recommendations.
    """
    __tablename__ = "user_item_interaction_history"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True)
    item_id: UUID = Field(index=True)
    
    first_shown_at: datetime = Field(default_factory=datetime.utcnow)
    last_shown_at: datetime = Field(default_factory=datetime.utcnow)
    times_shown: int = 1
    
    was_dismissed: bool = False
    was_disliked: bool = False
    was_liked: bool = False
    was_ordered: bool = False
    
    session_ids: List[str] = Field(default_factory=list, sa_column=Column(JSON))
