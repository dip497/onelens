"""User-related Pydantic schemas."""

from typing import List, Optional
from uuid import UUID

from pydantic import Field, validator

from .base import BaseCreateSchema, BaseUpdateSchema, BaseResponseSchema, PaginatedResponse


class UserBase(BaseCreateSchema):
    """Base User schema with common fields."""
    
    email: str = Field(..., description="User email address")
    name: str = Field(..., min_length=1, max_length=255, description="User full name")
    is_active: bool = Field(True, description="Whether the user is active")
    is_superuser: bool = Field(False, description="Whether the user has superuser privileges")


class UserCreate(UserBase):
    """Schema for creating a new User."""
    
    password: str = Field(..., min_length=8, description="User password (minimum 8 characters)")
    
    @validator('email')
    def validate_email(cls, v):
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError('Invalid email format')
        return v.lower()
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Name cannot be empty')
        return v.strip()
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class UserUpdate(BaseUpdateSchema):
    """Schema for updating an existing User."""
    
    email: Optional[str] = Field(None, description="User email address")
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="User full name")
    is_active: Optional[bool] = Field(None, description="Whether the user is active")
    is_superuser: Optional[bool] = Field(None, description="Whether the user has superuser privileges")
    
    @validator('name')
    def validate_name(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('Name cannot be empty')
        return v.strip() if v else v


class UserResponse(BaseResponseSchema):
    """Schema for User responses."""
    
    email: str
    name: str
    is_active: bool
    is_superuser: bool
    
    # Nested relationships
    created_epics: List[dict] = Field(default_factory=list, description="Epics created by this user")
    assigned_epics: List[dict] = Field(default_factory=list, description="Epics assigned to this user")
    
    # Computed fields
    total_created_epics: int = Field(0, description="Total number of epics created")
    total_assigned_epics: int = Field(0, description="Total number of epics assigned")
    
    @validator('created_epics', pre=True, always=True)
    def validate_created_epics(cls, v):
        if v is None:
            return []
        return v
    
    @validator('assigned_epics', pre=True, always=True)
    def validate_assigned_epics(cls, v):
        if v is None:
            return []
        return v


class UserListResponse(PaginatedResponse):
    """Paginated User list response."""
    
    items: List[UserResponse]


class UserSummary(BaseResponseSchema):
    """Minimal User schema for summary views."""
    
    email: str
    name: str
    is_active: bool
    total_created_epics: int = 0
    total_assigned_epics: int = 0


class UserPasswordUpdate(BaseUpdateSchema):
    """Schema for updating user password."""
    
    current_password: str = Field(..., description="Current password for verification")
    new_password: str = Field(..., min_length=8, description="New password (minimum 8 characters)")
    
    @validator('new_password')
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError('New password must be at least 8 characters long')
        return v


class UserActivationUpdate(BaseUpdateSchema):
    """Schema for updating user activation status."""
    
    is_active: bool = Field(..., description="Activation status")


class UserLogin(BaseCreateSchema):
    """Schema for user login."""
    
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class UserToken(BaseCreateSchema):
    """Schema for user authentication token."""
    
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    user: UserResponse = Field(..., description="User information")


class UserProfile(BaseResponseSchema):
    """Schema for user profile information."""
    
    email: str
    name: str
    is_active: bool
    is_superuser: bool
    
    # Activity statistics
    total_created_epics: int = Field(0, description="Total epics created")
    total_assigned_epics: int = Field(0, description="Total epics assigned")
    active_assigned_epics: int = Field(0, description="Currently active assigned epics")
    recent_activity: List[dict] = Field(default_factory=list, description="Recent activity")


class UserSearch(BaseCreateSchema):
    """Schema for user search parameters."""
    
    email: Optional[str] = Field(None, description="Search by email")
    name: Optional[str] = Field(None, description="Search by name")
    is_active: Optional[bool] = Field(None, description="Filter by active status")
    is_superuser: Optional[bool] = Field(None, description="Filter by superuser status")


class UserMetrics(BaseCreateSchema):
    """Schema for user metrics and statistics."""
    
    total_users: int = Field(0, description="Total number of users")
    active_users: int = Field(0, description="Number of active users")
    inactive_users: int = Field(0, description="Number of inactive users")
    superusers: int = Field(0, description="Number of superusers")
    users_with_created_epics: int = Field(0, description="Users who have created epics")
    users_with_assigned_epics: int = Field(0, description="Users with assigned epics")
    most_active_creators: List[dict] = Field(default_factory=list, description="Users who created most epics")
    most_assigned_users: List[dict] = Field(default_factory=list, description="Users with most assigned epics")