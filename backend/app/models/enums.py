import enum

class EpicStatus(str, enum.Enum):
    DRAFT = "Draft"
    ANALYSIS_PENDING = "Analysis Pending"
    ANALYZED = "Analyzed"
    APPROVED = "Approved"
    IN_PROGRESS = "In Progress"
    DELIVERED = "Delivered"

class MarketPosition(str, enum.Enum):
    LEADER = "Leader"
    CHALLENGER = "Challenger"
    VISIONARY = "Visionary"
    NICHE = "Niche"

class CompanySize(str, enum.Enum):
    STARTUP = "Startup"
    SMB = "SMB"
    ENTERPRISE = "Enterprise"
    LARGE_ENTERPRISE = "Large Enterprise"

class CustomerSegment(str, enum.Enum):
    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"
    ENTERPRISE = "Enterprise"

class CustomerVertical(str, enum.Enum):
    HEALTHCARE = "Healthcare"
    FINANCE = "Finance"
    TECHNOLOGY = "Technology"
    MANUFACTURING = "Manufacturing"
    RETAIL = "Retail"
    OTHER = "Other"

class UrgencyLevel(str, enum.Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

class RequestSource(str, enum.Enum):
    SALES_CALL = "Sales Call"
    SUPPORT_TICKET = "Support Ticket"
    USER_INTERVIEW = "User Interview"
    RFP = "RFP"

class ImpactLevel(str, enum.Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

class ComplexityLevel(str, enum.Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"

class AvailabilityStatus(str, enum.Enum):
    AVAILABLE = "Available"
    BETA = "Beta"
    PLANNED = "Planned"
    DISCONTINUED = "Discontinued"

class PricingTier(str, enum.Enum):
    FREE = "Free"
    BASIC = "Basic"
    PRO = "Pro"
    ENTERPRISE = "Enterprise"

class LocalPresence(str, enum.Enum):
    STRONG = "Strong"
    MEDIUM = "Medium"
    WEAK = "Weak"
    NONE = "None"

class OpportunityRating(str, enum.Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

class ProcessedStatus(str, enum.Enum):
    PENDING = "Pending"
    PROCESSING = "Processing"
    COMPLETE = "Complete"
    FAILED = "Failed"

class TShirtSize(str, enum.Enum):
    XS = "XS"
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"
    XXL = "XXL"

class CustomerSize(str, enum.Enum):
    SMB = "SMB"
    MID_MARKET = "Mid Market"
    ENTERPRISE = "Enterprise"
    ALL = "All"

class BattleCardStatus(str, enum.Enum):
    DRAFT = "Draft"
    PUBLISHED = "Published"
    ARCHIVED = "Archived"

class BattleCardSectionType(str, enum.Enum):
    WHY_WE_WIN = "Why We Win"
    COMPETITOR_STRENGTHS = "Competitor Strengths"
    OBJECTION_HANDLING = "Objection Handling"
    FEATURE_COMPARISON = "Feature Comparison"
    PRICING_COMPARISON = "Pricing Comparison"
    KEY_DIFFERENTIATORS = "Key Differentiators"

class ScrapingJobType(str, enum.Enum):
    FEATURES = "Features"
    PRICING = "Pricing"
    NEWS = "News"
    REVIEWS = "Reviews"
    FULL_SCAN = "Full Scan"

class ScrapingJobStatus(str, enum.Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"