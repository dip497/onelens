from sqlalchemy import Column, String, Text, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from .base import Base, TimestampMixin
from .enums import EpicStatus

class Epic(Base, TimestampMixin):
    __tablename__ = "epics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    business_justification = Column(Text)
    status = Column(Enum(EpicStatus), default=EpicStatus.DRAFT, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"))

    # Relationships
    creator = relationship("User", back_populates="created_epics", foreign_keys=[created_by])
    assignee = relationship("User", back_populates="assigned_epics", foreign_keys=[assigned_to])
    features = relationship("Feature", back_populates="epic", cascade="all, delete-orphan")