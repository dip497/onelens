from typing import Optional, TypeVar, Generic
from pydantic import BaseModel, ConfigDict
from datetime import datetime

T = TypeVar('T')

class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class TimestampSchema(BaseSchema):
    created_at: datetime
    updated_at: Optional[datetime] = None

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int

class PaginationParams(BaseModel):
    page: int = 1
    limit: int = 10

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.limit