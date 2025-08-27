from __future__ import annotations
from typing import Optional
from datetime import datetime
from uuid import uuid4, UUID
from sqlmodel import SQLModel, Field


class Interaction(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True)
    item_id: UUID = Field(index=True)
    type: str  # validated at service/router level
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Rating(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True)
    item_id: UUID = Field(index=True)
    rating: int
    liked: bool
    reasons: str = ""  # store JSON string to keep simple
    comment: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
