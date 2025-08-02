from sqlalchemy import Column, String, Enum, ForeignKey, Text, Integer, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from .base import Base, TimestampMixin
from .enums import CustomerSize, BattleCardStatus, BattleCardSectionType, ScrapingJobType, ScrapingJobStatus


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    tagline = Column(String(500))
    logo_url = Column(String(500))
    website = Column(String(500))

    # Relationships
    segments = relationship("ProductSegment", back_populates="product", cascade="all, delete-orphan")
    modules = relationship("ProductModule", back_populates="product", cascade="all, delete-orphan")
    battle_cards = relationship("BattleCard", back_populates="product", cascade="all, delete-orphan")


class ProductSegment(Base, TimestampMixin):
    __tablename__ = "product_segments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    target_market = Column(Text)
    customer_size = Column(Enum(CustomerSize))

    # Relationships
    product = relationship("Product", back_populates="segments")


class ProductModule(Base, TimestampMixin):
    __tablename__ = "product_modules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    icon = Column(String(100))
    order_index = Column(Integer, default=0)

    # Relationships
    product = relationship("Product", back_populates="modules")
    features = relationship("Feature", back_populates="module")  # Legacy - epic features assigned to modules
    module_features = relationship("ModuleFeature", back_populates="module", cascade="all, delete-orphan")  # New - dedicated module features


class BattleCard(Base, TimestampMixin):
    __tablename__ = "battle_cards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, default=1)
    status = Column(Enum(BattleCardStatus), default=BattleCardStatus.DRAFT)
    published_at = Column(DateTime(timezone=True))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))

    # Relationships
    product = relationship("Product", back_populates="battle_cards")
    competitor = relationship("Competitor", backref="battle_cards")
    sections = relationship("BattleCardSection", back_populates="battle_card", cascade="all, delete-orphan")
    created_by_user = relationship("User", backref="created_battle_cards")


class BattleCardSection(Base, TimestampMixin):
    __tablename__ = "battle_card_sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    battle_card_id = Column(UUID(as_uuid=True), ForeignKey("battle_cards.id", ondelete="CASCADE"), nullable=False)
    section_type = Column(Enum(BattleCardSectionType), nullable=False)
    content = Column(JSONB, nullable=False)
    order_index = Column(Integer, default=0)

    # Relationships
    battle_card = relationship("BattleCard", back_populates="sections")


class CompetitorScrapingJob(Base, TimestampMixin):
    __tablename__ = "competitor_scraping_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id = Column(UUID(as_uuid=True), ForeignKey("competitors.id", ondelete="CASCADE"), nullable=False)
    job_type = Column(Enum(ScrapingJobType), nullable=False)
    status = Column(Enum(ScrapingJobStatus), default=ScrapingJobStatus.PENDING)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    results = Column(JSONB)

    # Relationships
    competitor = relationship("Competitor", backref="scraping_jobs")