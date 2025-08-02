"""
Pydantic schemas for Module Features
"""

from datetime import datetime
from typing import Optional, Dict, List, Any
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.enums import AvailabilityStatus, ComplexityLevel


class ModuleFeatureBase(BaseModel):
    """Base schema for module features"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    value_proposition: Optional[str] = None
    is_key_differentiator: bool = False
    competitor_comparison: Optional[str] = None
    target_segment: Optional[str] = Field(None, max_length=100)
    status: AvailabilityStatus = AvailabilityStatus.AVAILABLE
    availability_date: Optional[str] = Field(None, max_length=50)
    implementation_complexity: ComplexityLevel = ComplexityLevel.MEDIUM
    adoption_rate: Optional[int] = Field(None, ge=0, le=100)
    success_metrics: Optional[str] = None  # JSON string
    customer_quotes: Optional[str] = None  # JSON string
    order_index: int = 0


class ModuleFeatureCreate(ModuleFeatureBase):
    """Schema for creating a module feature"""
    module_id: UUID
    epic_feature_id: Optional[UUID] = None


class ModuleFeatureUpdate(BaseModel):
    """Schema for updating a module feature"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    value_proposition: Optional[str] = None
    is_key_differentiator: Optional[bool] = None
    competitor_comparison: Optional[str] = None
    target_segment: Optional[str] = Field(None, max_length=100)
    status: Optional[AvailabilityStatus] = None
    availability_date: Optional[str] = Field(None, max_length=50)
    implementation_complexity: Optional[ComplexityLevel] = None
    adoption_rate: Optional[int] = Field(None, ge=0, le=100)
    success_metrics: Optional[str] = None
    customer_quotes: Optional[str] = None
    order_index: Optional[int] = None
    epic_feature_id: Optional[UUID] = None


class ModuleFeatureResponse(ModuleFeatureBase):
    """Schema for module feature responses"""
    id: UUID
    module_id: UUID
    epic_feature_id: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Optional nested data
    module_name: Optional[str] = None
    epic_feature_title: Optional[str] = None
    
    class Config:
        from_attributes = True


class ModuleFeatureListResponse(BaseModel):
    """Response for paginated module feature list"""
    items: List[ModuleFeatureResponse]
    total: int
    page: int
    size: int
    pages: int


class ModuleFeatureSummary(BaseModel):
    """Summary of module features for dashboard"""
    total_features: int
    key_differentiators: int
    active_features: int
    planned_features: int
    by_complexity: Dict[str, int]
    by_segment: Dict[str, int]