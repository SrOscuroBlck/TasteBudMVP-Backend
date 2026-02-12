from __future__ import annotations
from typing import Optional, Dict, Any, List
from uuid import uuid4, UUID
from datetime import datetime
from enum import Enum
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON


class IngestionSource(str, Enum):
    PDF = "pdf"
    IMAGE = "image"
    URL = "url"


class IngestionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVIEW_REQUIRED = "review_required"


class MenuUpload(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    restaurant_id: UUID = Field(index=True)
    source_type: IngestionSource
    status: IngestionStatus = Field(default=IngestionStatus.PENDING)
    
    file_path: Optional[str] = None
    source_url: Optional[str] = None
    original_filename: Optional[str] = None
    
    extracted_text: Optional[str] = None
    parsed_data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    
    items_created: int = 0
    items_failed: int = 0
    
    error_message: Optional[str] = None
    processing_time_seconds: Optional[float] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ParsedMenuItem(SQLModel):
    name: str
    description: str = ""
    price: Optional[float] = None
    
    ingredients: List[str] = Field(default_factory=list)
    allergens: List[str] = Field(default_factory=list)
    dietary_tags: List[str] = Field(default_factory=list)
    cuisine: List[str] = Field(default_factory=list)
    
    spice_level: Optional[int] = None
    cooking_method: Optional[str] = None
    course: Optional[str] = None
    
    inference_confidence: float = 1.0
    raw_text: Optional[str] = None


class MenuParsingResult(SQLModel):
    restaurant_name: Optional[str] = None
    restaurant_location: Optional[str] = None
    menu_items: List[ParsedMenuItem] = Field(default_factory=list)
    extraction_confidence: float = 1.0
    notes: str = ""
