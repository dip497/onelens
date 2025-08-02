"""RFP Processing Service for de-duplication and feature matching."""

from typing import List, Optional, Dict, Any
from uuid import UUID
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
import asyncio
from datetime import datetime
import re

from app.models.rfp import RFPDocument, RFPQAPair
from app.models.feature import Feature
from app.models.epic import Epic
from app.models.customer import FeatureRequest
from app.models.enums import ProcessedStatus, EpicStatus
from app.services.embedding import EmbeddingService


class RFPProcessor:
    """Service for processing RFP documents and matching features."""
    
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.similarity_threshold = 0.85
    
    async def find_similar_features(
        self,
        embedding: np.ndarray,
        threshold: float = 0.7,  # Lower threshold for better matching
        db: AsyncSession = None
    ) -> List[tuple[Feature, float]]:
        """Find features similar to the given embedding using vector search."""

        # Get all features
        result = await db.execute(select(Feature))
        features = result.scalars().all()

        similar_features = []

        for feature in features:
            # Skip if feature doesn't have description
            if not feature.description:
                continue

            # Generate embedding for feature if not cached
            feature_text = f"{feature.title} {feature.description}"
            feature_embedding = await self.embedding_service.generate_embedding(feature_text)

            # Calculate cosine similarity
            similarity = self._cosine_similarity(embedding, feature_embedding)

            if similarity >= threshold:
                similar_features.append((feature, similarity))

        # Sort by similarity and return features with scores
        similar_features.sort(key=lambda x: x[1], reverse=True)
        return similar_features
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)

    async def _create_feature_from_qa(
        self,
        qa_pair: RFPQAPair,
        customer_id: Optional[UUID],
        db: AsyncSession
    ) -> Feature:
        """Create a new feature from a Q&A pair."""

        # Extract feature title from question (clean and truncate)
        title = self._extract_feature_title(qa_pair.question)

        # Use answer as description
        description = qa_pair.answer.strip()

        # Get or create a default epic for RFP-generated features
        epic = await self._get_or_create_rfp_epic(db)

        # Create normalized text for searching
        normalized_text = f"{title} {description}".lower()

        # Create the feature
        feature = Feature(
            epic_id=epic.id,
            title=title,
            description=description,
            normalized_text=normalized_text,
            customer_request_count=1 if customer_id else 0
        )

        db.add(feature)
        await db.flush()  # Get the ID without committing

        # Create feature request if customer is specified
        if customer_id:
            feature_request = FeatureRequest(
                feature_id=feature.id,
                customer_id=customer_id,
                business_justification=f"Requested in RFP: {qa_pair.question}",
                source="rfp_analysis",
                request_details=qa_pair.answer
            )
            db.add(feature_request)

        return feature

    def _extract_feature_title(self, question: str) -> str:
        """Extract a clean feature title from a question."""

        # Remove common question words and clean up
        question = question.strip()

        # Remove question words at the beginning
        question_words = ['can', 'could', 'would', 'will', 'do', 'does', 'is', 'are', 'how', 'what', 'when', 'where', 'why', 'which']
        words = question.split()

        # Remove leading question words
        while words and words[0].lower() in question_words:
            words.pop(0)

        # Remove trailing question marks and punctuation
        if words:
            words[-1] = re.sub(r'[?!.]+$', '', words[-1])

        # Join and clean up
        title = ' '.join(words)

        # Capitalize first letter
        if title:
            title = title[0].upper() + title[1:]

        # Truncate to reasonable length
        if len(title) > 100:
            title = title[:97] + "..."

        return title or "Feature Request"

    async def _get_or_create_rfp_epic(self, db: AsyncSession) -> Epic:
        """Get or create an epic for RFP-generated features."""

        # Look for existing RFP epic
        result = await db.execute(
            select(Epic).filter(Epic.title == "RFP Generated Features")
        )
        epic = result.scalar_one_or_none()

        if not epic:
            # Create new epic for RFP features
            epic = Epic(
                title="RFP Generated Features",
                description="Features automatically generated from RFP analysis",
                status=EpicStatus.DRAFT
            )
            db.add(epic)
            await db.flush()

        return epic

    async def process_document(
        self,
        document_id: UUID,
        auto_link_features: bool = True,
        extract_business_context: bool = True,
        generate_feature_suggestions: bool = True,  # Changed default to True
        db: AsyncSession = None
    ) -> Dict[str, Any]:
        """Process an RFP document and extract insights."""

        # Get document and Q&A pairs
        result = await db.execute(select(RFPDocument).filter(RFPDocument.id == document_id))
        document = result.scalar_one_or_none()
        if not document:
            raise ValueError(f"Document {document_id} not found")

        result = await db.execute(select(RFPQAPair).filter(RFPQAPair.document_id == document_id))
        qa_pairs = result.scalars().all()
        
        results = {
            "document_id": document_id,
            "qa_pairs_processed": 0,
            "features_linked": 0,
            "new_features_created": 0,
            "business_context": {},
            "feature_suggestions": []
        }
        
        try:
            # Update status
            document.processed_status = ProcessedStatus.PROCESSING
            await db.commit()

            # Process each Q&A pair
            for qa_pair in qa_pairs:
                # Generate embedding
                text = f"{qa_pair.question} {qa_pair.answer}"
                embedding = await self.embedding_service.generate_embedding(text)

                if auto_link_features:
                    # Find similar features
                    similar_features = await self.find_similar_features(
                        embedding,
                        self.similarity_threshold,
                        db
                    )

                    if similar_features:
                        # Link to most similar feature
                        best_feature, similarity_score = similar_features[0]
                        qa_pair.feature_id = best_feature.id
                        results["features_linked"] += 1

                        # Update feature request count
                        best_feature.customer_request_count += 1

                        # Create feature request if customer is specified
                        if document.customer_id:
                            await self._increment_customer_request(
                                best_feature.id,
                                document.customer_id,
                                db
                            )

                        # Store similarity score in customer context
                        qa_pair.customer_context = qa_pair.customer_context or {}
                        qa_pair.customer_context["similarity_score"] = float(similarity_score)
                        qa_pair.customer_context["matched_feature"] = best_feature.title

                    else:
                        # Create new feature if no similar features found
                        if generate_feature_suggestions:
                            new_feature = await self._create_feature_from_qa(
                                qa_pair,
                                document.customer_id,
                                db
                            )
                            qa_pair.feature_id = new_feature.id
                            results["new_features_created"] += 1

                            # Store creation info in customer context
                            qa_pair.customer_context = qa_pair.customer_context or {}
                            qa_pair.customer_context["feature_created"] = True
                            qa_pair.customer_context["new_feature_title"] = new_feature.title

                results["qa_pairs_processed"] += 1

                # Commit periodically
                if results["qa_pairs_processed"] % 10 == 0:
                    await db.commit()
            
            # Extract business context
            if extract_business_context:
                results["business_context"] = await self._extract_business_context(
                    document,
                    qa_pairs,
                    db
                )
                document.business_context = results["business_context"]

            # Update document status
            document.processed_status = ProcessedStatus.COMPLETE
            document.processed_questions = results["qa_pairs_processed"]
            await db.commit()

        except Exception as e:
            # Handle errors
            document.processed_status = ProcessedStatus.FAILED
            document.business_context = document.business_context or {}
            document.business_context["error"] = str(e)
            await db.commit()
            raise
        
        return results
    
    async def _increment_customer_request(
        self,
        feature_id: UUID,
        customer_id: UUID,
        db: AsyncSession
    ):
        """Create a feature request record for the customer."""

        # Create a proper FeatureRequest record
        feature_request = FeatureRequest(
            feature_id=feature_id,
            customer_id=customer_id,
            business_justification="Requested in RFP analysis",
            source="rfp_analysis"
        )

        db.add(feature_request)
        # Note: Don't commit here, let the caller handle commits
    
    async def _generate_feature_suggestion(
        self,
        qa_pair: RFPQAPair,
        customer_id: Optional[UUID],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Generate a feature suggestion from a Q&A pair."""
        
        return {
            "suggested_name": qa_pair.question[:100],  # Truncate for name
            "description": f"Feature requested in RFP: {qa_pair.answer}",
            "source": "rfp_analysis",
            "qa_pair_id": str(qa_pair.id),
            "customer_id": str(customer_id) if customer_id else None,
            "confidence_score": 0.7  # Default confidence
        }
    
    async def _extract_business_context(
        self,
        document: RFPDocument,
        qa_pairs: List[RFPQAPair],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Extract business context from RFP document."""
        
        context = {
            "total_questions": len(qa_pairs),
            "extraction_timestamp": datetime.utcnow().isoformat(),
            "themes": [],
            "urgency_indicators": [],
            "technical_requirements": []
        }
        
        # Analyze Q&A pairs for patterns
        all_text = " ".join([f"{qa.question} {qa.answer}" for qa in qa_pairs])
        
        # Look for urgency indicators
        urgency_keywords = ["urgent", "asap", "immediately", "critical", "priority"]
        for keyword in urgency_keywords:
            if keyword.lower() in all_text.lower():
                context["urgency_indicators"].append(keyword)
        
        # Extract technical requirements (simplified)
        tech_keywords = ["api", "integration", "security", "performance", "scalability"]
        for keyword in tech_keywords:
            if keyword.lower() in all_text.lower():
                context["technical_requirements"].append(keyword)
        
        return context
    
    async def bulk_process_documents(
        self,
        document_ids: List[UUID],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Process multiple RFP documents in bulk."""
        
        results = {
            "total_documents": len(document_ids),
            "processed_successfully": 0,
            "failed": 0,
            "results": []
        }
        
        for doc_id in document_ids:
            try:
                result = await self.process_document(
                    doc_id,
                    auto_link_features=True,
                    extract_business_context=True,
                    db=db
                )
                results["processed_successfully"] += 1
                results["results"].append({
                    "document_id": str(doc_id),
                    "status": "success",
                    "details": result
                })
            except Exception as e:
                results["failed"] += 1
                results["results"].append({
                    "document_id": str(doc_id),
                    "status": "failed",
                    "error": str(e)
                })
        
        return results