from typing import Optional, List
from datetime import datetime
from uuid import UUID
from pydantic import Field

from app.schemas.base import BaseSchema, TimestampSchema, PaginatedResponse
from app.models.enums import EpicStatus

class EpicBase(BaseSchema):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    business_justification: Optional[str] = None
    assigned_to: Optional[UUID] = None

class EpicCreate(EpicBase):
    pass

class EpicUpdate(BaseSchema):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    business_justification: Optional[str] = None
    status: Optional[EpicStatus] = None
    assigned_to: Optional[UUID] = None

class EpicResponse(EpicBase, TimestampSchema):
    id: UUID
    status: EpicStatus
    created_by: Optional[UUID] = None
    features_count: Optional[int] = 0

class EpicWithFeatures(EpicResponse):
    features: List[dict] = []  # Will be populated with FeatureResponse dicts

class EpicListResponse(PaginatedResponse[EpicResponse]):
    pass

class EpicSummary(BaseSchema):
    status: EpicStatus
    count: int