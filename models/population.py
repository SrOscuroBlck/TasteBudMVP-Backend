from __future__ import annotations
from typing import Dict,List
from uuid import uuid4, UUID
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON


class TasteArchetype(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    description: str
    taste_vector: Dict[str, float] = Field(sa_column=Column(JSON))
    typical_cuisines: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    example_items: List[str] = Field(default_factory=list, sa_column=Column(JSON))


class PopulationStats(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    axis_prior_mean: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    axis_prior_sigma: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    cuisine_prior: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    item_popularity_global: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    item_popularity_by_restaurant: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    decay_half_life_days: int = 30
