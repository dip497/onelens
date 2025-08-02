from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

from app.models.enums import CustomerSize, BattleCardStatus, BattleCardSectionType, ScrapingJobType, ScrapingJobStatus


# Product Schemas
class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    tagline: Optional[str] = None
    logo_url: Optional[str] = None
    website: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tagline: Optional[str] = None
    logo_url: Optional[str] = None
    website: Optional[str] = None


class ProductResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    tagline: Optional[str]
    logo_url: Optional[str]
    website: Optional[str]
    created_at: datetime
    updated_at: datetime
    segments: List["ProductSegmentResponse"] = []
    modules: List["ProductModuleResponse"] = []

    class Config:
        from_attributes = True


# Product Segment Schemas
class ProductSegmentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    target_market: Optional[str] = None
    customer_size: Optional[CustomerSize] = None


class ProductSegmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    target_market: Optional[str] = None
    customer_size: Optional[CustomerSize] = None


class ProductSegmentResponse(BaseModel):
    id: UUID
    product_id: UUID
    name: str
    description: Optional[str]
    target_market: Optional[str]
    customer_size: Optional[CustomerSize]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Product Module Schemas
class ProductModuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    order_index: int = 0


class ProductModuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    order_index: Optional[int] = None


class ProductModuleResponse(BaseModel):
    id: UUID
    product_id: UUID
    name: str
    description: Optional[str]
    icon: Optional[str]
    order_index: int
    created_at: datetime
    updated_at: datetime
    feature_count: int = 0

    class Config:
        from_attributes = True


class ModuleReorderRequest(BaseModel):
    module_orders: List[Dict[str, Any]]  # [{"id": "uuid", "order_index": 0}, ...]


# Battle Card Schemas
class BattleCardSectionCreate(BaseModel):
    section_type: BattleCardSectionType
    content: Dict[str, Any]
    order_index: int = 0


class BattleCardSectionUpdate(BaseModel):
    section_type: Optional[BattleCardSectionType] = None
    content: Optional[Dict[str, Any]] = None
    order_index: Optional[int] = None


class BattleCardSectionResponse(BaseModel):
    id: UUID
    battle_card_id: UUID
    section_type: BattleCardSectionType
    content: Dict[str, Any]
    order_index: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BattleCardCreate(BaseModel):
    product_id: UUID
    competitor_id: UUID
    sections: List[BattleCardSectionCreate] = []


class BattleCardUpdate(BaseModel):
    status: Optional[BattleCardStatus] = None
    sections: Optional[List[BattleCardSectionUpdate]] = None


class BattleCardResponse(BaseModel):
    id: UUID
    product_id: UUID
    competitor_id: UUID
    version: int
    status: BattleCardStatus
    published_at: Optional[datetime]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    sections: List[BattleCardSectionResponse] = []
    product_name: Optional[str] = None
    competitor_name: Optional[str] = None

    class Config:
        from_attributes = True


class BattleCardGenerateRequest(BaseModel):
    competitor_id: UUID
    include_sections: List[BattleCardSectionType] = [
        BattleCardSectionType.WHY_WE_WIN,
        BattleCardSectionType.COMPETITOR_STRENGTHS,
        BattleCardSectionType.OBJECTION_HANDLING,
        BattleCardSectionType.FEATURE_COMPARISON,
        BattleCardSectionType.KEY_DIFFERENTIATORS
    ]


# Scraping Job Schemas
class CompetitorScrapingRequest(BaseModel):
    job_type: ScrapingJobType
    target_urls: Optional[List[str]] = []


class ScrapingJobResponse(BaseModel):
    id: UUID
    competitor_id: UUID
    job_type: ScrapingJobType
    status: ScrapingJobStatus
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    results: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Feature Assignment
class FeatureModuleAssignment(BaseModel):
    feature_id: UUID
    module_id: Optional[UUID]
    is_key_differentiator: bool = False


class ModuleFeaturesUpdate(BaseModel):
    feature_assignments: List[FeatureModuleAssignment]


# Update forward references
ProductResponse.model_rebuild()
BattleCardResponse.model_rebuild()