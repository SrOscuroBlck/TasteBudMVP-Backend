from __future__ import annotations
from typing import Dict
from uuid import uuid4, UUID
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON


class PopulationStats(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    axis_prior_mean: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    axis_prior_sigma: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    cuisine_prior: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    item_popularity_global: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    item_popularity_by_restaurant: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    decay_half_life_days: int = 30
