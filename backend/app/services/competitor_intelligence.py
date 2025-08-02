"""
Competitor Intelligence Service using Agno Agents
"""
from typing import Dict, Any, List, Optional
from uuid import UUID
import json
from agno.agent import Agent

# Create a simple Message class if not available
class Message:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

from app.models import Competitor, CompetitorFeature
from app.models.enums import AvailabilityStatus, PricingTier
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


class CompetitorIntelligenceService:
    """Service for gathering competitor intelligence using Agno agents"""
    
    def __init__(self):
        # Initialize the competitive analysis agent
        self.competitive_agent = Agent(
            name="competitive_analysis_agent",
            model="claude-3-sonnet-20240229",
            system_prompt="""You are a competitive intelligence analyst.
            Your role is to research competitor feature offerings and market positioning.
            
            For each competitor, you should:
            1. Identify key product features and capabilities
            2. Analyze strengths and weaknesses
            3. Determine pricing tiers and availability
            4. Assess market positioning
            
            Provide structured data that can be parsed and stored."""
        )
    
    async def analyze_competitor(
        self, 
        competitor: Competitor,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Analyze a competitor using AI agent"""
        
        # Prepare the analysis prompt
        prompt = f"""
        Analyze the competitor: {competitor.name}
        Website: {competitor.website or 'Not provided'}
        
        Please research and provide:
        1. List of main product features (name, description, availability status)
        2. Pricing tiers and models
        3. Key strengths (top 3)
        4. Key weaknesses (top 3)
        5. Target market segments
        6. Recent product updates or announcements
        
        Format the response as structured JSON.
        """
        
        # Use the agent to analyze
        response = await self.competitive_agent.generate(
            messages=[Message(role="user", content=prompt)]
        )
        
        # Parse the response
        try:
            analysis_data = json.loads(response.content)
        except json.JSONDecodeError:
            # Fallback if response isn't valid JSON
            analysis_data = {
                "features": [],
                "analysis": response.content
            }
        
        # Store discovered features
        if "features" in analysis_data:
            await self._store_competitor_features(
                competitor.id,
                analysis_data["features"],
                db
            )
        
        return analysis_data
    
    async def compare_with_our_product(
        self,
        competitor_id: UUID,
        product_id: UUID,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Compare competitor with our product"""
        
        # Get our product features
        from app.models import Product, ProductModule, Feature
        
        result = await db.execute(
            select(Feature)
            .join(ProductModule, Feature.module_id == ProductModule.id)
            .where(ProductModule.product_id == product_id)
        )
        our_features = result.scalars().all()
        
        # Get competitor features
        result = await db.execute(
            select(CompetitorFeature)
            .where(CompetitorFeature.competitor_id == competitor_id)
        )
        competitor_features = result.scalars().all()
        
        # Prepare comparison prompt
        our_feature_list = [
            {"name": f.title, "description": f.description, "is_key": f.is_key_differentiator}
            for f in our_features
        ]
        
        competitor_feature_list = [
            {"name": f.feature_name, "description": f.feature_description}
            for f in competitor_features
        ]
        
        prompt = f"""
        Compare our product features with the competitor's features.
        
        Our features:
        {json.dumps(our_feature_list, indent=2)}
        
        Competitor features:
        {json.dumps(competitor_feature_list, indent=2)}
        
        Provide:
        1. Features we have that they don't (competitive advantages)
        2. Features they have that we don't (gaps to consider)
        3. Features both have (how do we differentiate?)
        4. Recommended talking points for sales
        5. Suggested objection handling
        
        Format as structured JSON.
        """
        
        response = await self.competitive_agent.generate(
            messages=[Message(role="user", content=prompt)]
        )
        
        try:
            comparison_data = json.loads(response.content)
        except json.JSONDecodeError:
            comparison_data = {"analysis": response.content}
        
        return comparison_data
    
    async def generate_battle_card_content(
        self,
        competitor_id: UUID,
        product_id: UUID,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Generate battle card content using AI"""
        
        # Get comparison data
        comparison = await self.compare_with_our_product(
            competitor_id, product_id, db
        )
        
        # Get competitor details
        result = await db.execute(
            select(Competitor).where(Competitor.id == competitor_id)
        )
        competitor = result.scalar_one()
        
        prompt = f"""
        Based on the competitive analysis, generate battle card content for sales team.
        
        Competitor: {competitor.name}
        Market Position: {competitor.market_position or 'Unknown'}
        
        Comparison Data:
        {json.dumps(comparison, indent=2)}
        
        Generate sections for:
        1. Why We Win (3 key points with evidence and talk tracks)
        2. Competitor Strengths (acknowledge their strengths and how to counter)
        3. Objection Handling (common objections and responses)
        4. Key Differentiators (what makes us unique)
        
        Format each section as structured JSON with specific fields.
        """
        
        response = await self.competitive_agent.generate(
            messages=[Message(role="user", content=prompt)]
        )
        
        try:
            battle_card_content = json.loads(response.content)
        except json.JSONDecodeError:
            # Fallback structure
            battle_card_content = {
                "why_we_win": [
                    {
                        "point": "Superior Technology",
                        "evidence": "AI-powered analysis",
                        "talk_track": "Our AI provides insights competitors can't match"
                    }
                ],
                "competitor_strengths": [
                    {
                        "strength": "Market presence",
                        "counter": "Focus on innovation and customer success",
                        "response": "While they have market share, we offer better value"
                    }
                ],
                "objection_handling": [
                    {
                        "objection": "Your solution is newer/less proven",
                        "response": "Our modern architecture provides advantages...",
                        "proof_points": ["Customer testimonials", "Performance metrics"]
                    }
                ],
                "key_differentiators": [
                    {
                        "feature": "AI-Powered Analytics",
                        "description": "Unique insights from our AI engine",
                        "value_prop": "Faster, more accurate decisions"
                    }
                ]
            }
        
        return battle_card_content
    
    async def _store_competitor_features(
        self,
        competitor_id: UUID,
        features: List[Dict[str, Any]],
        db: AsyncSession
    ):
        """Store discovered competitor features"""
        for feature_data in features:
            # Check if feature already exists
            result = await db.execute(
                select(CompetitorFeature)
                .where(
                    CompetitorFeature.competitor_id == competitor_id,
                    CompetitorFeature.feature_name == feature_data.get("name", "")
                )
            )
            existing = result.scalar_one_or_none()
            
            if not existing:
                # Create new feature
                new_feature = CompetitorFeature(
                    competitor_id=competitor_id,
                    feature_name=feature_data.get("name", "Unknown Feature"),
                    feature_description=feature_data.get("description", ""),
                    availability=self._map_availability(feature_data.get("availability", "available")),
                    pricing_tier=self._map_pricing_tier(feature_data.get("pricing", "unknown")),
                    strengths=feature_data.get("strengths", ""),
                    weaknesses=feature_data.get("weaknesses", "")
                )
                db.add(new_feature)
        
        await db.commit()
    
    def _map_availability(self, status: str) -> AvailabilityStatus:
        """Map text availability to enum"""
        status_lower = status.lower()
        if "beta" in status_lower:
            return AvailabilityStatus.BETA
        elif "planned" in status_lower or "coming" in status_lower:
            return AvailabilityStatus.PLANNED
        elif "discontinued" in status_lower or "deprecated" in status_lower:
            return AvailabilityStatus.DISCONTINUED
        else:
            return AvailabilityStatus.AVAILABLE
    
    def _map_pricing_tier(self, pricing: str) -> Optional[PricingTier]:
        """Map text pricing to enum"""
        pricing_lower = pricing.lower()
        if "free" in pricing_lower:
            return PricingTier.FREE
        elif "basic" in pricing_lower or "starter" in pricing_lower:
            return PricingTier.BASIC
        elif "pro" in pricing_lower or "professional" in pricing_lower:
            return PricingTier.PRO
        elif "enterprise" in pricing_lower:
            return PricingTier.ENTERPRISE
        return None