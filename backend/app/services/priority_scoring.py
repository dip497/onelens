from typing import Dict, List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import logging

from app.models import (
    Feature, FeatureRequest, Customer, 
    TrendAnalysis, BusinessImpactAnalysis, 
    MarketOpportunityAnalysis, PriorityScore
)
from app.models.enums import CustomerSegment, UrgencyLevel

logger = logging.getLogger(__name__)

class PriorityScoringService:
    """Service for calculating feature priority scores"""
    
    # Customer segment weights
    CUSTOMER_WEIGHTS = {
        CustomerSegment.SMALL: 1.0,
        CustomerSegment.MEDIUM: 2.5,
        CustomerSegment.LARGE: 5.0,
        CustomerSegment.ENTERPRISE: 10.0
    }
    
    # Urgency multipliers
    URGENCY_MULTIPLIERS = {
        UrgencyLevel.CRITICAL: 2.0,
        UrgencyLevel.HIGH: 1.5,
        UrgencyLevel.MEDIUM: 1.0,
        UrgencyLevel.LOW: 0.5
    }
    
    # Scoring weights
    WEIGHTS = {
        "customer_impact": 0.30,
        "trend_alignment": 0.20,
        "business_impact": 0.25,
        "market_opportunity": 0.20,
        "segment_diversity": 0.05
    }
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def calculate_priority_score(self, feature_id: UUID) -> PriorityScore:
        """
        Calculate priority score for a feature based on multiple factors
        
        Args:
            feature_id: UUID of the feature to score
            
        Returns:
            PriorityScore object with calculated scores
        """
        # Get feature data
        feature = await self._get_feature(feature_id)
        if not feature:
            raise ValueError(f"Feature {feature_id} not found")
        
        # Calculate individual scores
        customer_score = await self._calculate_customer_impact_score(feature_id)
        trend_score = await self._calculate_trend_alignment_score(feature_id)
        business_score = await self._calculate_business_impact_score(feature_id)
        market_score = await self._calculate_market_opportunity_score(feature_id)
        diversity_score = await self._calculate_segment_diversity_score(feature_id)
        
        # Calculate weighted final score
        final_score = (
            (customer_score * self.WEIGHTS["customer_impact"]) +
            (trend_score * self.WEIGHTS["trend_alignment"]) +
            (business_score * self.WEIGHTS["business_impact"]) +
            (market_score * self.WEIGHTS["market_opportunity"]) +
            (diversity_score * self.WEIGHTS["segment_diversity"])
        )
        
        # Create priority score record
        priority_score = PriorityScore(
            feature_id=feature_id,
            final_score=min(final_score, 100.0),
            customer_impact_score=customer_score,
            trend_alignment_score=trend_score,
            business_impact_score=business_score,
            market_opportunity_score=market_score,
            segment_diversity_score=diversity_score,
            calculation_metadata={
                "weights": self.WEIGHTS,
                "timestamp": datetime.utcnow().isoformat(),
                "algorithm_version": "1.0"
            },
            algorithm_version="1.0"
        )
        
        # Save to database
        self.db.add(priority_score)
        await self.db.commit()
        await self.db.refresh(priority_score)
        
        logger.info(f"Calculated priority score for feature {feature_id}: {final_score}")
        
        return priority_score
    
    async def _get_feature(self, feature_id: UUID) -> Optional[Feature]:
        """Get feature by ID"""
        query = select(Feature).where(Feature.id == feature_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def _calculate_customer_impact_score(self, feature_id: UUID) -> float:
        """
        Calculate customer impact score based on requests and customer segments
        
        Returns score 0-100
        """
        # Get all feature requests with customer data
        query = select(FeatureRequest, Customer).join(
            Customer, FeatureRequest.customer_id == Customer.id
        ).where(FeatureRequest.feature_id == feature_id)
        
        result = await self.db.execute(query)
        requests_with_customers = result.all()
        
        if not requests_with_customers:
            return 0.0
        
        total_weight = 0.0
        for request, customer in requests_with_customers:
            # Get customer segment weight
            segment_weight = self.CUSTOMER_WEIGHTS.get(customer.segment, 1.0)
            
            # Get urgency multiplier
            urgency_multiplier = self.URGENCY_MULTIPLIERS.get(request.urgency, 1.0)
            
            # Calculate weighted score
            total_weight += segment_weight * urgency_multiplier
        
        # Normalize to 0-100 scale (cap at 100)
        return min(total_weight * 5, 100.0)  # Multiply by 5 to scale appropriately
    
    async def _calculate_trend_alignment_score(self, feature_id: UUID) -> float:
        """
        Calculate trend alignment score based on AI analysis
        
        Returns score 0-100
        """
        # Get latest trend analysis
        query = select(TrendAnalysis).where(
            TrendAnalysis.feature_id == feature_id
        ).order_by(TrendAnalysis.created_at.desc()).limit(1)
        
        result = await self.db.execute(query)
        trend_analysis = result.scalar_one_or_none()
        
        if not trend_analysis:
            return 50.0  # Default neutral score if no analysis
        
        # Convert trend score (0-10) to 0-100 scale
        return float(trend_analysis.trend_score) * 10 if trend_analysis.trend_score else 50.0
    
    async def _calculate_business_impact_score(self, feature_id: UUID) -> float:
        """
        Calculate business impact score
        
        Returns score 0-100
        """
        # Get latest business impact analysis
        query = select(BusinessImpactAnalysis).where(
            BusinessImpactAnalysis.feature_id == feature_id
        ).order_by(BusinessImpactAnalysis.created_at.desc()).limit(1)
        
        result = await self.db.execute(query)
        business_analysis = result.scalar_one_or_none()
        
        if not business_analysis:
            return 50.0  # Default neutral score if no analysis
        
        return float(business_analysis.impact_score) if business_analysis.impact_score else 50.0
    
    async def _calculate_market_opportunity_score(self, feature_id: UUID) -> float:
        """
        Calculate market opportunity score based on competitive gap
        
        Higher score when fewer competitors provide the feature
        Returns score 0-100
        """
        # Get latest market opportunity analysis
        query = select(MarketOpportunityAnalysis).where(
            MarketOpportunityAnalysis.feature_id == feature_id
        ).order_by(MarketOpportunityAnalysis.created_at.desc()).limit(1)
        
        result = await self.db.execute(query)
        market_analysis = result.scalar_one_or_none()
        
        if not market_analysis or not market_analysis.total_competitors_analyzed:
            return 50.0  # Default neutral score if no analysis
        
        # Calculate gap ratio (higher is better)
        gap_ratio = (market_analysis.competitors_not_providing / 
                    market_analysis.total_competitors_analyzed)
        
        return gap_ratio * 100
    
    async def _calculate_segment_diversity_score(self, feature_id: UUID) -> float:
        """
        Calculate segment diversity score based on unique customer segments
        
        Returns score 0-100
        """
        # Get unique customer segments that have requested this feature
        query = select(func.count(func.distinct(Customer.segment))).select_from(
            FeatureRequest
        ).join(
            Customer, FeatureRequest.customer_id == Customer.id
        ).where(FeatureRequest.feature_id == feature_id)
        
        unique_segments = await self.db.scalar(query)
        
        if not unique_segments:
            return 0.0
        
        # Max 4 segments (Small, Medium, Large, Enterprise) = 100 score
        return min(unique_segments * 25, 100.0)
    
    async def recalculate_all_scores(self, epic_id: Optional[UUID] = None) -> List[PriorityScore]:
        """
        Recalculate priority scores for all features or features in a specific epic
        
        Args:
            epic_id: Optional epic ID to limit recalculation
            
        Returns:
            List of updated priority scores
        """
        # Get features to recalculate
        query = select(Feature)
        if epic_id:
            query = query.where(Feature.epic_id == epic_id)
        
        result = await self.db.execute(query)
        features = result.scalars().all()
        
        updated_scores = []
        for feature in features:
            try:
                score = await self.calculate_priority_score(feature.id)
                updated_scores.append(score)
            except Exception as e:
                logger.error(f"Error calculating score for feature {feature.id}: {e}")
        
        return updated_scores
    
    async def get_feature_ranking(self, epic_id: Optional[UUID] = None, limit: int = 10) -> List[Dict]:
        """
        Get ranked features by priority score
        
        Args:
            epic_id: Optional epic ID to filter features
            limit: Number of top features to return
            
        Returns:
            List of features with scores, ranked by priority
        """
        # Build query for features with their latest priority scores
        query = select(
            Feature,
            PriorityScore.final_score,
            PriorityScore.calculated_at
        ).join(
            PriorityScore, Feature.id == PriorityScore.feature_id
        )
        
        if epic_id:
            query = query.where(Feature.epic_id == epic_id)
        
        # Get only the latest score for each feature
        subquery = select(
            PriorityScore.feature_id,
            func.max(PriorityScore.calculated_at).label("latest_calculation")
        ).group_by(PriorityScore.feature_id).subquery()
        
        query = query.join(
            subquery,
            (PriorityScore.feature_id == subquery.c.feature_id) &
            (PriorityScore.calculated_at == subquery.c.latest_calculation)
        )
        
        # Order by score descending
        query = query.order_by(PriorityScore.final_score.desc()).limit(limit)
        
        result = await self.db.execute(query)
        ranked_features = []
        
        for idx, (feature, score, calculated_at) in enumerate(result):
            ranked_features.append({
                "rank": idx + 1,
                "feature_id": feature.id,
                "feature_title": feature.title,
                "epic_id": feature.epic_id,
                "priority_score": float(score),
                "calculated_at": calculated_at
            })
        
        return ranked_features