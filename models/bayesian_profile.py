from __future__ import annotations
from typing import Dict, Optional
from datetime import datetime
from uuid import uuid4, UUID
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON
import numpy as np

from models.user import TASTE_AXES


class BayesianTasteProfile(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True, unique=True)
    
    alpha_params: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    beta_params: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    
    mean_preferences: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    uncertainties: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    
    cuisine_alpha: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    cuisine_beta: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    cuisine_means: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    def update_cached_statistics(self) -> None:
        for axis in TASTE_AXES:
            if axis not in self.alpha_params or axis not in self.beta_params:
                continue
            
            alpha = self.alpha_params[axis]
            beta = self.beta_params[axis]
            total = alpha + beta
            
            if total > 0:
                self.mean_preferences[axis] = alpha / total
            else:
                self.mean_preferences[axis] = 0.5
            
            if total > 0:
                variance = (alpha * beta) / ((total ** 2) * (total + 1))
                self.uncertainties[axis] = float(np.sqrt(variance))
            else:
                self.uncertainties[axis] = 0.5
        
        for cuisine in list(self.cuisine_alpha.keys()):
            if cuisine not in self.cuisine_beta:
                continue
            
            alpha = self.cuisine_alpha[cuisine]
            beta = self.cuisine_beta[cuisine]
            total = alpha + beta
            
            if total > 0:
                self.cuisine_means[cuisine] = alpha / total
            else:
                self.cuisine_means[cuisine] = 0.5
    
    def sample_taste_preferences(self) -> Dict[str, float]:
        sampled = {}
        for axis in TASTE_AXES:
            if axis not in self.alpha_params or axis not in self.beta_params:
                sampled[axis] = 0.5
                continue
            
            alpha = max(0.01, self.alpha_params[axis])
            beta = max(0.01, self.beta_params[axis])
            
            sampled[axis] = float(np.random.beta(alpha, beta))
        
        return sampled
    
    def get_cuisine_preference(self, cuisine: str) -> float:
        return self.cuisine_means.get(cuisine, 0.5)
