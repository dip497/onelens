"""Customer-related Pydantic schemas."""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import Field, validator

from ..models.enums import CustomerSegment, CustomerVertical, ImpactLevel
from .base import BaseCreateSchema, BaseUpdateSchema, BaseResponseSchema, PaginatedResponse


class CustomerBase(BaseCreateSchema):
    """Base Customer schema with common fields."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Customer name")
    segment: Optional[CustomerSegment] = Field(None, description="Customer segment")
    vertical: Optional[CustomerVertical] = Field(None, description="Customer vertical/industry")
    arr: Optional[Decimal] = Field(None, ge=0, description="Annual Recurring Revenue")
    employee_count: Optional[int] = Field(None, ge=0, description="Number of employees")
    geographic_region: Optional[str] = Field(None, max_length=100, description="Geographic region")
    contract_end_date: Optional[date] = Field(None, description="Contract end date")
    strategic_importance: Optional[ImpactLevel] = Field(None, description="Strategic importance level")


class CustomerCreate(CustomerBase):
    """Schema for creating a new Customer."""
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Customer name cannot be empty')
        return v.strip()
    
    @validator('arr')
    def validate_arr(cls, v):
        if v is not None and v < 0:
            raise ValueError('ARR cannot be negative')
        return v
    
    @validator('employee_count')
    def validate_employee_count(cls, v):
        if v is not None and v < 0:
            raise ValueError('Employee count cannot be negative')
        return v


class CustomerUpdate(BaseUpdateSchema):
    """Schema for updating an existing Customer."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Customer name")
    segment: Optional[CustomerSegment] = Field(None, description="Customer segment")
    vertical: Optional[CustomerVertical] = Field(None, description="Customer vertical/industry")
    arr: Optional[Decimal] = Field(None, ge=0, description="Annual Recurring Revenue")
    employee_count: Optional[int] = Field(None, ge=0, description="Number of employees")
    geographic_region: Optional[str] = Field(None, max_length=100, description="Geographic region")
    contract_end_date: Optional[date] = Field(None, description="Contract end date")
    strategic_importance: Optional[ImpactLevel] = Field(None, description="Strategic importance level")
    
    @validator('name')
    def validate_name(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('Customer name cannot be empty')
        return v.strip() if v else v
    
    @validator('arr')
    def validate_arr(cls, v):
        if v is not None and v < 0:
            raise ValueError('ARR cannot be negative')
        return v
    
    @validator('employee_count')
    def validate_employee_count(cls, v):
        if v is not None and v < 0:
            raise ValueError('Employee count cannot be negative')
        return v


class CustomerResponse(BaseResponseSchema):
    """Schema for Customer responses."""
    
    name: str
    segment: Optional[CustomerSegment]
    vertical: Optional[CustomerVertical]
    arr: Optional[Decimal]
    employee_count: Optional[int]
    geographic_region: Optional[str]
    contract_end_date: Optional[date]
    strategic_importance: Optional[ImpactLevel]
    
    # Nested relationships
    feature_requests: List[dict] = Field(default_factory=list, description="Customer's feature requests")
    rfp_documents: List[dict] = Field(default_factory=list, description="Customer's RFP documents")
    
    # Computed fields
    total_feature_requests: int = Field(0, description="Total number of feature requests")
    total_estimated_deal_impact: Optional[Decimal] = Field(None, description="Total estimated deal impact")
    days_to_contract_end: Optional[int] = Field(None, description="Days until contract ends")
    
    @validator('feature_requests', pre=True, always=True)
    def validate_feature_requests(cls, v):
        if v is None:
            return []
        return v
    
    @validator('rfp_documents', pre=True, always=True)
    def validate_rfp_documents(cls, v):
        if v is None:
            return []
        return v


class CustomerListResponse(PaginatedResponse):
    """Paginated Customer list response."""
    
    items: List[CustomerResponse]


class CustomerSummary(BaseResponseSchema):
    """Minimal Customer schema for summary views."""
    
    name: str
    segment: Optional[CustomerSegment]
    vertical: Optional[CustomerVertical]
    arr: Optional[Decimal]
    strategic_importance: Optional[ImpactLevel]
    total_feature_requests: int = 0


class CustomerSearch(BaseCreateSchema):
    """Schema for customer search parameters."""
    
    name: Optional[str] = Field(None, description="Search by customer name")
    segment: Optional[CustomerSegment] = Field(None, description="Filter by customer segment")
    vertical: Optional[CustomerVertical] = Field(None, description="Filter by customer vertical")
    min_arr: Optional[Decimal] = Field(None, ge=0, description="Minimum ARR filter")
    max_arr: Optional[Decimal] = Field(None, ge=0, description="Maximum ARR filter")
    geographic_region: Optional[str] = Field(None, description="Filter by geographic region")
    strategic_importance: Optional[ImpactLevel] = Field(None, description="Filter by strategic importance")
    contract_ending_within_days: Optional[int] = Field(None, ge=0, description="Contracts ending within X days")
    
    @validator('max_arr')
    def validate_arr_range(cls, v, values):
        min_arr = values.get('min_arr')
        if v is not None and min_arr is not None and v < min_arr:
            raise ValueError('max_arr must be greater than or equal to min_arr')
        return v


class CustomerMetrics(BaseCreateSchema):
    """Schema for customer metrics and analytics."""
    
    total_customers: int = Field(0, description="Total number of customers")
    customers_by_segment: dict = Field(default_factory=dict, description="Customer count by segment")
    customers_by_vertical: dict = Field(default_factory=dict, description="Customer count by vertical")
    total_arr: Decimal = Field(Decimal('0'), description="Total ARR across all customers")
    average_arr: Decimal = Field(Decimal('0'), description="Average ARR per customer")
    contracts_expiring_30_days: int = Field(0, description="Contracts expiring in 30 days")
    contracts_expiring_90_days: int = Field(0, description="Contracts expiring in 90 days")
    top_requesting_customers: List[dict] = Field(default_factory=list, description="Customers with most feature requests")