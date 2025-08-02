from typing import List, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Product, Competitor, Feature, CompetitorFeature, ProductModule
from app.models.enums import BattleCardSectionType
from app.schemas.product import BattleCardSectionCreate


class BattleCardGenerator:
    """Service for generating battle card content using AI and data analysis"""
    
    async def generate_battle_card(
        self,
        product: Product,
        competitor: Competitor,
        include_sections: List[BattleCardSectionType],
        db: AsyncSession
    ) -> List[BattleCardSectionCreate]:
        """Generate battle card sections based on product and competitor data"""
        sections = []
        
        # Load product features and modules
        product_features = await self._get_product_features(product.id, db)
        competitor_features = await self._get_competitor_features(competitor.id, db)
        
        for section_type in include_sections:
            if section_type == BattleCardSectionType.WHY_WE_WIN:
                content = await self._generate_why_we_win(product_features, competitor_features)
            elif section_type == BattleCardSectionType.COMPETITOR_STRENGTHS:
                content = await self._generate_competitor_strengths(competitor, competitor_features)
            elif section_type == BattleCardSectionType.OBJECTION_HANDLING:
                content = await self._generate_objection_handling(product_features, competitor_features)
            elif section_type == BattleCardSectionType.FEATURE_COMPARISON:
                content = await self._generate_feature_comparison(product_features, competitor_features)
            elif section_type == BattleCardSectionType.KEY_DIFFERENTIATORS:
                content = await self._generate_key_differentiators(product_features, competitor_features)
            else:
                content = {"message": "Section not implemented yet"}
            
            sections.append(BattleCardSectionCreate(
                section_type=section_type,
                content=content,
                order_index=len(sections)
            ))
        
        return sections
    
    async def _get_product_features(self, product_id: UUID, db: AsyncSession) -> List[Feature]:
        """Get all features for a product through its modules"""
        result = await db.execute(
            select(Feature)
            .join(ProductModule, Feature.module_id == ProductModule.id)
            .where(ProductModule.product_id == product_id)
            .options(selectinload(Feature.module))
        )
        return result.scalars().all()
    
    async def _get_competitor_features(self, competitor_id: UUID, db: AsyncSession) -> List[CompetitorFeature]:
        """Get all features for a competitor"""
        result = await db.execute(
            select(CompetitorFeature)
            .where(CompetitorFeature.competitor_id == competitor_id)
        )
        return result.scalars().all()
    
    async def _generate_why_we_win(
        self,
        product_features: List[Feature],
        competitor_features: List[CompetitorFeature]
    ) -> Dict[str, Any]:
        """Generate 'Why We Win' section content"""
        # TODO: Implement AI-powered analysis
        # For now, return a structured placeholder
        key_differentiators = [f for f in product_features if f.is_key_differentiator]
        
        return {
            "points": [
                {
                    "point": f.title,
                    "evidence": f.description or "Feature advantage",
                    "talk_track": f"Our {f.title} provides unique value through {f.description}"
                }
                for f in key_differentiators[:3]
            ] if key_differentiators else [
                {
                    "point": "Advanced Features",
                    "evidence": "Comprehensive feature set",
                    "talk_track": "Our platform offers advanced capabilities"
                }
            ]
        }
    
    async def _generate_competitor_strengths(
        self,
        competitor: Competitor,
        competitor_features: List[CompetitorFeature]
    ) -> Dict[str, Any]:
        """Generate 'Competitor Strengths' section content"""
        # TODO: Implement AI-powered analysis
        strengths = []
        
        if competitor.market_position:
            strengths.append({
                "strength": f"{competitor.market_position} market position",
                "counter": "Focus on innovation and customer success",
                "response": "While they have market presence, we offer more innovative solutions"
            })
        
        for feature in competitor_features[:2]:
            if feature.strengths:
                strengths.append({
                    "strength": feature.feature_name,
                    "counter": "Our differentiated approach",
                    "response": feature.weaknesses or "We provide a better alternative"
                })
        
        return {"strengths": strengths}
    
    async def _generate_objection_handling(
        self,
        product_features: List[Feature],
        competitor_features: List[CompetitorFeature]
    ) -> Dict[str, Any]:
        """Generate 'Objection Handling' section content"""
        # TODO: Implement AI-powered analysis
        objections = []
        
        # Find features competitor has that we might not
        competitor_feature_names = {cf.feature_name for cf in competitor_features}
        our_feature_names = {f.title for f in product_features}
        
        missing_features = competitor_feature_names - our_feature_names
        
        for missing in list(missing_features)[:3]:
            objections.append({
                "objection": f"Your product lacks {missing}",
                "response": f"We've taken a different approach that provides better overall value",
                "proof_points": ["Customer success stories", "ROI data"]
            })
        
        return {"objections": objections}
    
    async def _generate_feature_comparison(
        self,
        product_features: List[Feature],
        competitor_features: List[CompetitorFeature]
    ) -> Dict[str, Any]:
        """Generate 'Feature Comparison' section content"""
        our_features = [f.title for f in product_features]
        their_features = [f.feature_name for f in competitor_features]
        
        return {
            "our_product": {
                "features": our_features[:10],
                "unique_features": list(set(our_features) - set(their_features))[:5]
            },
            "competitor": {
                "features": their_features[:10],
                "missing_features": list(set(our_features) - set(their_features))[:5]
            }
        }
    
    async def _generate_key_differentiators(
        self,
        product_features: List[Feature],
        competitor_features: List[CompetitorFeature]
    ) -> Dict[str, Any]:
        """Generate 'Key Differentiators' section content"""
        differentiators = []
        
        for feature in product_features:
            if feature.is_key_differentiator:
                differentiators.append({
                    "feature": feature.title,
                    "description": feature.description,
                    "value_prop": f"Unique capability that drives customer success"
                })
        
        return {"differentiators": differentiators[:5]}