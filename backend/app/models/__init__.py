from .base import Base
from .user import User
from .epic import Epic
from .feature import Feature
from .customer import Customer, FeatureRequest
from .competitor import Competitor, CompetitorFeature, CompetitorGeographicPresence
from .analysis import (
    TrendAnalysis,
    BusinessImpactAnalysis,
    MarketOpportunityAnalysis,
    GeographicAnalysis,
    PriorityScore,
    FeatureAnalysisReport
)
from .rfp import RFPDocument, RFPQAPair
from .product import (
    Product,
    ProductSegment,
    ProductModule,
    BattleCard,
    BattleCardSection,
    CompetitorScrapingJob
)
from .module_feature import ModuleFeature

__all__ = [
    "Base",
    "User",
    "Epic",
    "Feature",
    "Customer",
    "FeatureRequest",
    "Competitor",
    "CompetitorFeature",
    "CompetitorGeographicPresence",
    "TrendAnalysis",
    "BusinessImpactAnalysis",
    "MarketOpportunityAnalysis",
    "GeographicAnalysis",
    "PriorityScore",
    "FeatureAnalysisReport",
    "RFPDocument",
    "RFPQAPair",
    "Product",
    "ProductSegment",
    "ProductModule",
    "BattleCard",
    "BattleCardSection",
    "CompetitorScrapingJob",
    "ModuleFeature"
]