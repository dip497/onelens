"""Competitor-related Pydantic schemas."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import Field, validator, HttpUrl

from ..models.enums import (
    MarketPosition, CompanySize, AvailabilityStatus, 
    PricingTier, LocalPresence
)
from .base import BaseCreateSchema, BaseUpdateSchema, BaseResponseSchema, PaginatedResponse


class CompetitorBase(BaseCreateSchema):
    """Base Competitor schema with common fields."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Competitor name")
    website: Optional[str] = Field(None, max_length=500, description="Competitor website URL")
    market_position: Optional[MarketPosition] = Field(None, description="Market position classification")
    primary_markets: Optional[List[str]] = Field(None, description="Primary markets (e.g., ['US', 'EU', 'APAC'])")
    company_size: Optional[CompanySize] = Field(None, description="Company size classification")
    funding_stage: Optional[str] = Field(None, max_length=100, description="Funding stage")


class CompetitorCreate(CompetitorBase):
    """Schema for creating a new Competitor."""
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Competitor name cannot be empty')
        return v.strip()
    
    @validator('website')
    def validate_website(cls, v):
        if v and not v.startswith(('http://', 'https://')):
            v = f'https://{v}'
        return v
    
    @validator('primary_markets')
    def validate_primary_markets(cls, v):
        if v is not None:
            # Remove duplicates and empty strings
            return list(set(filter(None, [market.strip() for market in v])))
        return v


class CompetitorUpdate(BaseUpdateSchema):
    """Schema for updating an existing Competitor."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Competitor name")
    website: Optional[str] = Field(None, max_length=500, description="Competitor website URL")
    market_position: Optional[MarketPosition] = Field(None, description="Market position classification")
    primary_markets: Optional[List[str]] = Field(None, description="Primary markets")
    company_size: Optional[CompanySize] = Field(None, description="Company size classification")
    funding_stage: Optional[str] = Field(None, max_length=100, description="Funding stage")
    
    @validator('name')
    def validate_name(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('Competitor name cannot be empty')
        return v.strip() if v else v
    
    @validator('website')
    def validate_website(cls, v):
        if v and not v.startswith(('http://', 'https://')):
            v = f'https://{v}'
        return v
    
    @validator('primary_markets')
    def validate_primary_markets(cls, v):
        if v is not None:
            return list(set(filter(None, [market.strip() for market in v])))
        return v


class CompetitorResponse(BaseResponseSchema):
    """Schema for Competitor responses."""
    
    name: str
    website: Optional[str]
    market_position: Optional[MarketPosition]
    primary_markets: Optional[List[str]]
    company_size: Optional[CompanySize]
    funding_stage: Optional[str]
    
    # Nested relationships
    features: List[dict] = Field(default_factory=list, description="Competitor features")
    geographic_presence: List[dict] = Field(default_factory=list, description="Geographic presence data")
    
    # Computed fields
    total_features: int = Field(0, description="Total number of features tracked")
    markets_count: int = Field(0, description="Number of markets where competitor is present")
    
    @validator('features', pre=True, always=True)
    def validate_features(cls, v):
        if v is None:
            return []
        return v
    
    @validator('geographic_presence', pre=True, always=True)
    def validate_geographic_presence(cls, v):
        if v is None:
            return []
        return v


class CompetitorListResponse(PaginatedResponse):
    """Paginated Competitor list response."""
    
    items: List[CompetitorResponse]


class CompetitorSummary(BaseResponseSchema):
    """Minimal Competitor schema for summary views."""
    
    name: str
    market_position: Optional[MarketPosition]
    company_size: Optional[CompanySize]
    total_features: int = 0
    markets_count: int = 0


# Competitor Feature schemas
class CompetitorFeatureBase(BaseCreateSchema):
    """Base CompetitorFeature schema with common fields."""
    
    feature_name: Optional[str] = Field(None, max_length=255, description="Feature name")
    feature_description: Optional[str] = Field(None, description="Feature description")
    availability: Optional[AvailabilityStatus] = Field(None, description="Feature availability status")
    pricing_tier: Optional[PricingTier] = Field(None, description="Pricing tier for this feature")
    strengths: Optional[str] = Field(None, description="Feature strengths")
    weaknesses: Optional[str] = Field(None, description="Feature weaknesses")
    source_url: Optional[str] = Field(None, max_length=500, description="Source URL for verification")


class CompetitorFeatureCreate(CompetitorFeatureBase):
    """Schema for creating a new CompetitorFeature."""
    
    competitor_id: UUID = Field(..., description="ID of the competitor this feature belongs to")
    
    @validator('source_url')
    def validate_source_url(cls, v):
        if v and not v.startswith(('http://', 'https://')):
            v = f'https://{v}'
        return v


class CompetitorFeatureUpdate(BaseUpdateSchema):
    """Schema for updating an existing CompetitorFeature."""
    
    feature_name: Optional[str] = Field(None, max_length=255, description="Feature name")
    feature_description: Optional[str] = Field(None, description="Feature description")
    availability: Optional[AvailabilityStatus] = Field(None, description="Feature availability status")
    pricing_tier: Optional[PricingTier] = Field(None, description="Pricing tier for this feature")
    strengths: Optional[str] = Field(None, description="Feature strengths")
    weaknesses: Optional[str] = Field(None, description="Feature weaknesses")
    source_url: Optional[str] = Field(None, max_length=500, description="Source URL for verification")
    
    @validator('source_url')
    def validate_source_url(cls, v):
        if v and not v.startswith(('http://', 'https://')):
            v = f'https://{v}'
        return v


class CompetitorFeatureResponse(BaseResponseSchema):
    """Schema for CompetitorFeature responses."""
    
    competitor_id: UUID
    feature_name: Optional[str]
    feature_description: Optional[str]
    availability: Optional[AvailabilityStatus]
    pricing_tier: Optional[PricingTier]
    strengths: Optional[str]
    weaknesses: Optional[str]
    last_verified: Optional[datetime]
    source_url: Optional[str]
    
    # Nested relationships
    competitor: Optional[dict] = Field(None, description="Associated competitor information")


# Competitor Geographic Presence schemas
class CompetitorGeographicPresenceBase(BaseCreateSchema):
    """Base CompetitorGeographicPresence schema with common fields."""
    
    country: Optional[str] = Field(None, max_length=100, description="Country name")
    market_share_percentage: Optional[Decimal] = Field(
        None, 
        ge=0, 
        le=100, 
        description="Market share percentage in this country"
    )
    local_presence: Optional[LocalPresence] = Field(None, description="Local presence strength")
    key_customers: Optional[List[str]] = Field(None, description="Key customers in this country")


class CompetitorGeographicPresenceCreate(CompetitorGeographicPresenceBase):
    """Schema for creating a new CompetitorGeographicPresence."""
    
    competitor_id: UUID = Field(..., description="ID of the competitor")
    
    @validator('market_share_percentage')
    def validate_market_share(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError('Market share percentage must be between 0 and 100')
        return v
    
    @validator('key_customers')
    def validate_key_customers(cls, v):
        if v is not None:
            return list(set(filter(None, [customer.strip() for customer in v])))
        return v


class CompetitorGeographicPresenceUpdate(BaseUpdateSchema):
    """Schema for updating an existing CompetitorGeographicPresence."""
    
    country: Optional[str] = Field(None, max_length=100, description="Country name")
    market_share_percentage: Optional[Decimal] = Field(
        None, 
        ge=0, 
        le=100, 
        description="Market share percentage in this country"
    )
    local_presence: Optional[LocalPresence] = Field(None, description="Local presence strength")
    key_customers: Optional[List[str]] = Field(None, description="Key customers in this country")
    
    @validator('market_share_percentage')
    def validate_market_share(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError('Market share percentage must be between 0 and 100')
        return v
    
    @validator('key_customers')
    def validate_key_customers(cls, v):
        if v is not None:
            return list(set(filter(None, [customer.strip() for customer in v])))
        return v


class CompetitorGeographicPresenceResponse(BaseResponseSchema):
    """Schema for CompetitorGeographicPresence responses."""
    
    competitor_id: UUID
    country: Optional[str]
    market_share_percentage: Optional[Decimal]
    local_presence: Optional[LocalPresence]
    key_customers: Optional[List[str]]
    
    # Nested relationships
    competitor: Optional[dict] = Field(None, description="Associated competitor information")


class CompetitorAnalysis(BaseCreateSchema):
    """Schema for competitor analysis results."""
    
    competitor_id: UUID
    total_features_analyzed: int = Field(0, description="Total features analyzed")
    features_available: int = Field(0, description="Features currently available")
    features_in_beta: int = Field(0, description="Features in beta")
    features_planned: int = Field(0, description="Features planned")
    feature_gaps: List[str] = Field(default_factory=list, description="Features they don't have")
    competitive_advantages: List[str] = Field(default_factory=list, description="Their competitive advantages")
    market_coverage: dict = Field(default_factory=dict, description="Geographic market coverage analysis")


class CompetitorComparison(BaseCreateSchema):
    """Schema for comparing multiple competitors."""
    
    competitor_ids: List[UUID] = Field(..., min_items=2, description="List of competitor IDs to compare")
    feature_comparison: Optional[dict] = Field(None, description="Feature-by-feature comparison")
    market_position_analysis: Optional[dict] = Field(None, description="Market position analysis")
    geographic_coverage_comparison: Optional[dict] = Field(None, description="Geographic coverage comparison")
    
    @validator('competitor_ids')
    def validate_competitor_ids(cls, v):
        if len(v) < 2:
            raise ValueError('At least 2 competitors are required for comparison')
        return list(set(v))  # Remove duplicates