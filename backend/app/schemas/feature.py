from typing import Optional, List
from datetime import datetime
from uuid import UUID
from pydantic import Field

from app.schemas.base import BaseSchema, TimestampSchema, PaginatedResponse
from app.models.enums import UrgencyLevel, RequestSource

class FeatureBase(BaseSchema):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None

class FeatureCreate(FeatureBase):
    epic_id: UUID

class FeatureCreateInEpic(FeatureBase):
    """Schema for creating a feature within an epic context (epic_id provided in URL)"""
    pass

class FeatureUpdate(BaseSchema):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None

class FeatureResponse(FeatureBase, TimestampSchema):
    id: UUID
    epic_id: UUID
    customer_request_count: int = 0

class PriorityScoreResponse(BaseSchema):
    id: UUID
    feature_id: UUID
    final_score: float
    customer_impact_score: float
    trend_alignment_score: float
    business_impact_score: float
    market_opportunity_score: float
    segment_diversity_score: float
    calculated_at: datetime

class FeatureWithAnalysis(FeatureResponse):
    priority_score: Optional[PriorityScoreResponse] = None

class FeatureListResponse(PaginatedResponse[FeatureResponse]):
    pass

class FeatureRequestCreate(BaseSchema):
    customer_id: UUID
    urgency: UrgencyLevel
    business_justification: Optional[str] = None
    estimated_deal_impact: Optional[float] = None
    source: Optional[RequestSource] = None
    request_details: Optional[str] = None

class FeatureRequestResponse(FeatureRequestCreate, TimestampSchema):
    id: UUID
    feature_id: UUID

class FeatureAnalysisRequest(BaseSchema):
    analysis_types: Optional[List[str]] = None