# TODO: Re-enable when sentence-transformers is needed
# from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List, Union
import asyncio
from functools import lru_cache

from app.core.config import settings

class EmbeddingService:
    """Service for generating text embeddings using sentence-transformers"""

    def __init__(self):
        self.model_name = settings.EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION
        self._model = None

    @property
    def model(self):
        """Lazy load the model"""
        # TODO: Re-enable when sentence-transformers is needed
        # if self._model is None:
        #     self._model = SentenceTransformer(self.model_name)
        # return self._model
        raise NotImplementedError("Embedding service is currently disabled")

    async def generate_embedding(self, text: Union[str, List[str]]) -> Union[np.ndarray, List[np.ndarray]]:
        """
        Generate embeddings for text asynchronously

        Args:
            text: Single text string or list of texts

        Returns:
            Numpy array of embeddings (using simple text-based features for now)
        """
        # Use simple text-based features until sentence-transformers is enabled
        if isinstance(text, str):
            return self._generate_simple_embedding(text)
        else:
            return [self._generate_simple_embedding(t) for t in text]

    def _generate_embedding_sync(self, text: Union[str, List[str]]) -> Union[np.ndarray, List[np.ndarray]]:
        """Synchronous embedding generation"""
        # TODO: Re-enable when sentence-transformers is needed
        # if isinstance(text, str):
        #     # Single text
        #     embedding = self.model.encode(text, convert_to_numpy=True)
        #     return embedding
        # else:
        #     # Multiple texts
        #     embeddings = self.model.encode(text, convert_to_numpy=True)
        #     return embeddings

        # Return dummy embedding for now
        if isinstance(text, str):
            return np.zeros(self.dimension, dtype=np.float32)
        else:
            return [np.zeros(self.dimension, dtype=np.float32) for _ in text]
    
    async def batch_generate_embeddings(self, texts: List[str], batch_size: int = 32) -> List[np.ndarray]:
        """
        Generate embeddings for multiple texts in batches
        
        Args:
            texts: List of text strings
            batch_size: Number of texts to process at once
            
        Returns:
            List of numpy arrays
        """
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = await self.generate_embedding(batch)
            all_embeddings.extend(embeddings)
        
        return all_embeddings

    def _generate_simple_embedding(self, text: str) -> np.ndarray:
        """
        Generate a simple embedding based on text features.
        This is a temporary solution until sentence-transformers is enabled.
        """
        import re
        from collections import Counter

        # Normalize text
        text = text.lower().strip()

        # Extract features
        words = re.findall(r'\b\w+\b', text)
        word_count = len(words)
        unique_words = len(set(words))

        # Character-level features
        char_count = len(text)
        digit_count = len(re.findall(r'\d', text))

        # Common tech keywords (for feature matching)
        tech_keywords = [
            'api', 'integration', 'security', 'performance', 'scalability',
            'authentication', 'authorization', 'database', 'analytics',
            'reporting', 'dashboard', 'notification', 'email', 'mobile',
            'web', 'cloud', 'backup', 'export', 'import', 'sync',
            'real-time', 'batch', 'automation', 'workflow', 'approval',
            'user', 'admin', 'role', 'permission', 'audit', 'log'
        ]

        # Business keywords
        business_keywords = [
            'revenue', 'cost', 'profit', 'customer', 'client', 'sales',
            'marketing', 'support', 'service', 'quality', 'compliance',
            'regulation', 'process', 'efficiency', 'productivity', 'roi'
        ]

        # Count keyword occurrences
        tech_score = sum(1 for keyword in tech_keywords if keyword in text)
        business_score = sum(1 for keyword in business_keywords if keyword in text)

        # Create embedding vector
        embedding = np.array([
            word_count / 100.0,  # Normalized word count
            unique_words / 100.0,  # Normalized unique word count
            char_count / 1000.0,  # Normalized character count
            digit_count / 10.0,  # Normalized digit count
            tech_score / 10.0,  # Tech keyword density
            business_score / 10.0,  # Business keyword density
            len(re.findall(r'[.!?]', text)) / 10.0,  # Sentence count
            len(re.findall(r'[A-Z]', text)) / 10.0,  # Capital letter count
        ], dtype=np.float32)

        # Pad or truncate to match expected dimension
        if len(embedding) < self.dimension:
            padding = np.zeros(self.dimension - len(embedding), dtype=np.float32)
            embedding = np.concatenate([embedding, padding])
        else:
            embedding = embedding[:self.dimension]

        return embedding
    
    def compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Compute cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Similarity score between 0 and 1
        """
        # Normalize vectors
        norm1 = embedding1 / np.linalg.norm(embedding1)
        norm2 = embedding2 / np.linalg.norm(embedding2)
        
        # Compute cosine similarity
        similarity = np.dot(norm1, norm2)
        
        # Convert to 0-1 range
        return float((similarity + 1) / 2)
    
    def find_similar_embeddings(
        self,
        query_embedding: np.ndarray,
        embeddings: List[np.ndarray],
        threshold: float = 0.7,
        top_k: int = 10
    ) -> List[tuple[int, float]]:
        """
        Find similar embeddings from a list
        
        Args:
            query_embedding: Query embedding to compare against
            embeddings: List of embeddings to search
            threshold: Minimum similarity threshold
            top_k: Maximum number of results to return
            
        Returns:
            List of (index, similarity_score) tuples
        """
        similarities = []
        
        for idx, embedding in enumerate(embeddings):
            similarity = self.compute_similarity(query_embedding, embedding)
            if similarity >= threshold:
                similarities.append((idx, similarity))
        
        # Sort by similarity descending
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        return similarities[:top_k]

# Singleton instance
_embedding_service = None

def get_embedding_service() -> EmbeddingService:
    """Get singleton embedding service instance"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service