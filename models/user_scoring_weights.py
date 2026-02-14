from __future__ import annotations
from typing import Dict, Optional
from datetime import datetime
from uuid import uuid4, UUID
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON


class UserScoringWeights(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True, unique=True)
    
    taste_weight: float = 0.5
    cuisine_weight: float = 0.2
    popularity_weight: float = 0.15
    exploration_weight: float = 0.15
    
    learning_rate: float = 0.01
    momentum: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    
    feedback_count: int = 0
    last_calibration_at: Optional[datetime] = None
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    def normalize_weights(self) -> None:
        total = (
            self.taste_weight +
            self.cuisine_weight +
            self.popularity_weight +
            self.exploration_weight
        )
        
        if total > 0:
            self.taste_weight /= total
            self.cuisine_weight /= total
            self.popularity_weight /= total
            self.exploration_weight /= total
    
    def get_weights_dict(self) -> Dict[str, float]:
        return {
            "taste": self.taste_weight,
            "cuisine": self.cuisine_weight,
            "popularity": self.popularity_weight,
            "exploration": self.exploration_weight
        }
