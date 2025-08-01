from typing import List, Dict, Any, Optional
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.models import Epic, Feature, Customer, FeatureRequest, Competitor, CompetitorFeature
from app.services.agno_chromadb_knowledge import ChromaDBKnowledge
from app.services.chromadb_service import chromadb_service

logger = logging.getLogger(__name__)

class KnowledgeLoader:
    """Service for loading OneLens data into the knowledge base"""
    
    def __init__(self, knowledge_base: ChromaDBKnowledge = None):
        self.knowledge_base = knowledge_base or ChromaDBKnowledge()
    
    async def load_all_data(self, recreate: bool = False) -> Dict[str, int]:
        """
        Load all OneLens data into the knowledge base
        
        Args:
            recreate: Whether to recreate the knowledge base from scratch
            
        Returns:
            Dictionary with counts of loaded items
        """
        if recreate:
            logger.info("Recreating knowledge base...")
            self.knowledge_base.clear()
        
        counts = {}
        
        async with AsyncSessionLocal() as db:
            # Load epics
            counts["epics"] = await self._load_epics(db)
            
            # Load features
            counts["features"] = await self._load_features(db)
            
            # Load customers
            counts["customers"] = await self._load_customers(db)
            
            # Load feature requests
            counts["feature_requests"] = await self._load_feature_requests(db)
            
            # Load competitors
            counts["competitors"] = await self._load_competitors(db)
            
            # Load competitor features
            counts["competitor_features"] = await self._load_competitor_features(db)
        
        total_loaded = sum(counts.values())
        logger.info(f"Loaded {total_loaded} total items into knowledge base: {counts}")
        
        return counts
    
    async def _load_epics(self, db: AsyncSession) -> int:
        """Load epics into knowledge base"""
        try:
            query = select(Epic)
            result = await db.execute(query)
            epics = result.scalars().all()
            
            documents = []
            metadatas = []
            ids = []
            
            for epic in epics:
                # Create document text
                text_parts = [f"Epic: {epic.title}"]
                if epic.description:
                    text_parts.append(f"Description: {epic.description}")
                if epic.business_justification:
                    text_parts.append(f"Business Justification: {epic.business_justification}")
                
                text = "\n".join(text_parts)
                documents.append(text)
                
                # Create metadata
                metadata = {
                    "type": "epic",
                    "id": str(epic.id),
                    "title": epic.title,
                    "status": epic.status.value if epic.status else None,
                    "priority": epic.priority.value if epic.priority else None,
                    "created_at": epic.created_at.isoformat() if epic.created_at else None
                }
                metadatas.append(metadata)
                
                ids.append(f"epic_{epic.id}")
            
            if documents:
                chromadb_service.add_documents(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
            
            logger.info(f"Loaded {len(documents)} epics into knowledge base")
            return len(documents)
            
        except Exception as e:
            logger.error(f"Error loading epics: {e}")
            return 0
    
    async def _load_features(self, db: AsyncSession) -> int:
        """Load features into knowledge base"""
        try:
            query = select(Feature)
            result = await db.execute(query)
            features = result.scalars().all()
            
            documents = []
            metadatas = []
            ids = []
            
            for feature in features:
                # Create document text
                text_parts = [f"Feature: {feature.title}"]
                if feature.description:
                    text_parts.append(f"Description: {feature.description}")
                
                text = "\n".join(text_parts)
                documents.append(text)
                
                # Create metadata
                metadata = {
                    "type": "feature",
                    "id": str(feature.id),
                    "title": feature.title,
                    "epic_id": str(feature.epic_id) if feature.epic_id else None,
                    "customer_request_count": feature.customer_request_count,
                    "created_at": feature.created_at.isoformat() if feature.created_at else None
                }
                metadatas.append(metadata)
                
                ids.append(f"feature_{feature.id}")
            
            if documents:
                chromadb_service.add_documents(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
            
            logger.info(f"Loaded {len(documents)} features into knowledge base")
            return len(documents)
            
        except Exception as e:
            logger.error(f"Error loading features: {e}")
            return 0
    
    async def _load_customers(self, db: AsyncSession) -> int:
        """Load customers into knowledge base"""
        try:
            query = select(Customer)
            result = await db.execute(query)
            customers = result.scalars().all()
            
            documents = []
            metadatas = []
            ids = []
            
            for customer in customers:
                # Create document text
                text_parts = [f"Customer: {customer.name}"]
                if customer.segment:
                    text_parts.append(f"Segment: {customer.segment.value}")
                if customer.vertical:
                    text_parts.append(f"Vertical: {customer.vertical.value}")
                if customer.geographic_region:
                    text_parts.append(f"Region: {customer.geographic_region}")
                if customer.arr:
                    text_parts.append(f"ARR: ${customer.arr}")
                
                text = "\n".join(text_parts)
                documents.append(text)
                
                # Create metadata
                metadata = {
                    "type": "customer",
                    "id": str(customer.id),
                    "name": customer.name,
                    "segment": customer.segment.value if customer.segment else None,
                    "vertical": customer.vertical.value if customer.vertical else None,
                    "geographic_region": customer.geographic_region,
                    "arr": float(customer.arr) if customer.arr else None,
                    "created_at": customer.created_at.isoformat() if customer.created_at else None
                }
                metadatas.append(metadata)
                
                ids.append(f"customer_{customer.id}")
            
            if documents:
                chromadb_service.add_documents(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
            
            logger.info(f"Loaded {len(documents)} customers into knowledge base")
            return len(documents)
            
        except Exception as e:
            logger.error(f"Error loading customers: {e}")
            return 0
    
    async def _load_feature_requests(self, db: AsyncSession) -> int:
        """Load feature requests into knowledge base"""
        try:
            query = select(FeatureRequest).join(Customer).join(Feature)
            result = await db.execute(query)
            requests = result.scalars().all()
            
            documents = []
            metadatas = []
            ids = []
            
            for request in requests:
                # Create document text
                text_parts = [f"Feature Request from {request.customer.name if request.customer else 'Unknown Customer'}"]
                text_parts.append(f"Feature: {request.feature.title if request.feature else 'Unknown Feature'}")
                if request.business_justification:
                    text_parts.append(f"Business Justification: {request.business_justification}")
                if request.urgency:
                    text_parts.append(f"Urgency: {request.urgency.value}")
                
                text = "\n".join(text_parts)
                documents.append(text)
                
                # Create metadata
                metadata = {
                    "type": "feature_request",
                    "id": str(request.id),
                    "customer_id": str(request.customer_id) if request.customer_id else None,
                    "feature_id": str(request.feature_id) if request.feature_id else None,
                    "urgency": request.urgency.value if request.urgency else None,
                    "created_at": request.created_at.isoformat() if request.created_at else None
                }
                metadatas.append(metadata)
                
                ids.append(f"feature_request_{request.id}")
            
            if documents:
                chromadb_service.add_documents(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
            
            logger.info(f"Loaded {len(documents)} feature requests into knowledge base")
            return len(documents)
            
        except Exception as e:
            logger.error(f"Error loading feature requests: {e}")
            return 0
    
    async def _load_competitors(self, db: AsyncSession) -> int:
        """Load competitors into knowledge base"""
        try:
            query = select(Competitor)
            result = await db.execute(query)
            competitors = result.scalars().all()
            
            documents = []
            metadatas = []
            ids = []
            
            for competitor in competitors:
                # Create document text
                text_parts = [f"Competitor: {competitor.name}"]
                if competitor.description:
                    text_parts.append(f"Description: {competitor.description}")
                if competitor.market_position:
                    text_parts.append(f"Market Position: {competitor.market_position.value}")
                if competitor.website:
                    text_parts.append(f"Website: {competitor.website}")
                
                text = "\n".join(text_parts)
                documents.append(text)
                
                # Create metadata
                metadata = {
                    "type": "competitor",
                    "id": str(competitor.id),
                    "name": competitor.name,
                    "market_position": competitor.market_position.value if competitor.market_position else None,
                    "website": competitor.website,
                    "created_at": competitor.created_at.isoformat() if competitor.created_at else None
                }
                metadatas.append(metadata)
                
                ids.append(f"competitor_{competitor.id}")
            
            if documents:
                chromadb_service.add_documents(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
            
            logger.info(f"Loaded {len(documents)} competitors into knowledge base")
            return len(documents)
            
        except Exception as e:
            logger.error(f"Error loading competitors: {e}")
            return 0
    
    async def _load_competitor_features(self, db: AsyncSession) -> int:
        """Load competitor features into knowledge base"""
        try:
            query = select(CompetitorFeature).join(Competitor)
            result = await db.execute(query)
            comp_features = result.scalars().all()
            
            documents = []
            metadatas = []
            ids = []
            
            for comp_feature in comp_features:
                # Create document text
                text_parts = [f"Competitor Feature: {comp_feature.feature_name}"]
                text_parts.append(f"Competitor: {comp_feature.competitor.name if comp_feature.competitor else 'Unknown'}")
                if comp_feature.description:
                    text_parts.append(f"Description: {comp_feature.description}")
                if comp_feature.pricing_tier:
                    text_parts.append(f"Pricing Tier: {comp_feature.pricing_tier}")
                
                text = "\n".join(text_parts)
                documents.append(text)
                
                # Create metadata
                metadata = {
                    "type": "competitor_feature",
                    "id": str(comp_feature.id),
                    "feature_name": comp_feature.feature_name,
                    "competitor_id": str(comp_feature.competitor_id) if comp_feature.competitor_id else None,
                    "pricing_tier": comp_feature.pricing_tier,
                    "created_at": comp_feature.created_at.isoformat() if comp_feature.created_at else None
                }
                metadatas.append(metadata)
                
                ids.append(f"competitor_feature_{comp_feature.id}")
            
            if documents:
                chromadb_service.add_documents(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
            
            logger.info(f"Loaded {len(documents)} competitor features into knowledge base")
            return len(documents)
            
        except Exception as e:
            logger.error(f"Error loading competitor features: {e}")
            return 0

# Global instance
knowledge_loader = KnowledgeLoader()
