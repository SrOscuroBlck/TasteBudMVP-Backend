from __future__ import annotations
from typing import Optional, Dict, List, Any
from datetime import datetime
from uuid import uuid4, UUID
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON


class EvaluationMetric(SQLModel, table=True):
    __tablename__ = "evaluation_metric"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_id: Optional[UUID] = Field(default=None, index=True)
    user_id: Optional[UUID] = Field(default=None, index=True)
    session_id: Optional[UUID] = Field(default=None, index=True)
    
    metric_type: str = Field(index=True)
    metric_name: str
    metric_value: float
    
    metric_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)


class OfflineEvaluation(SQLModel, table=True):
    __tablename__ = "offline_evaluation"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    evaluation_name: str = Field(index=True)
    algorithm_name: str
    
    ndcg_at_5: Optional[float] = None
    ndcg_at_10: Optional[float] = None
    ndcg_at_20: Optional[float] = None
    
    diversity_score: Optional[float] = None
    coverage_score: Optional[float] = None
    
    mean_taste_similarity: Optional[float] = None
    mean_exploration_bonus: Optional[float] = None
    
    test_set_size: int
    train_set_size: int
    
    temporal_split_date: Optional[datetime] = None
    
    evaluation_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class OnlineEvaluationMetrics(SQLModel, table=True):
    __tablename__ = "online_evaluation_metrics"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True)
    
    time_period_start: datetime = Field(index=True)
    time_period_end: datetime
    
    total_recommendations_shown: int = 0
    total_likes: int = 0
    total_dislikes: int = 0
    total_selections: int = 0
    total_dismissals: int = 0
    
    like_ratio: Optional[float] = None
    selection_ratio: Optional[float] = None
    engagement_ratio: Optional[float] = None
    
    avg_time_to_decision_seconds: Optional[float] = None
    
    avg_diversity_score: Optional[float] = None
    avg_novelty_score: Optional[float] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ABTestExperiment(SQLModel, table=True):
    __tablename__ = "ab_test_experiment"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    experiment_name: str = Field(unique=True, index=True)
    description: str
    
    algorithm_a_name: str
    algorithm_b_name: str
    
    start_date: datetime = Field(default_factory=datetime.utcnow)
    end_date: Optional[datetime] = None
    
    status: str = Field(default="active", index=True)
    
    users_in_a: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    users_in_b: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    
    interleaving_method: str = Field(default="team_draft")
    
    results_summary: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class InterleavingResult(SQLModel, table=True):
    __tablename__ = "interleaving_result"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    experiment_id: UUID = Field(index=True)
    user_id: UUID = Field(index=True)
    session_id: UUID = Field(index=True)
    
    algorithm_a_items: List[str] = Field(sa_column=Column(JSON))
    algorithm_b_items: List[str] = Field(sa_column=Column(JSON))
    interleaved_items: List[str] = Field(sa_column=Column(JSON))
    
    clicks_on_a: int = 0
    clicks_on_b: int = 0
    
    likes_on_a: int = 0
    likes_on_b: int = 0
    
    selections_on_a: int = 0
    selections_on_b: int = 0
    
    winner: Optional[str] = None
    
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
