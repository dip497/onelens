import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional, Union
import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

class ChromaDBService:
    """Service for managing ChromaDB operations"""
    
    def __init__(self, db_path: str = None, collection_name: str = None):
        self.db_path = db_path or settings.CHROMA_DB_PATH
        self.collection_name = collection_name or settings.CHROMA_COLLECTION_NAME
        self._client = None
        self._collection = None
        
        # Ensure the database directory exists
        Path(self.db_path).mkdir(parents=True, exist_ok=True)
    
    @property
    def client(self):
        """Lazy load ChromaDB client"""
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=self.db_path,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
        return self._client
    
    @property
    def collection(self):
        """Get or create the collection"""
        if self._collection is None:
            try:
                # Try to get existing collection
                self._collection = self.client.get_collection(name=self.collection_name)
                logger.info(f"Using existing ChromaDB collection: {self.collection_name}")
            except Exception:
                # Create new collection if it doesn't exist
                self._collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={"description": "OneLens knowledge base"}
                )
                logger.info(f"Created new ChromaDB collection: {self.collection_name}")
        return self._collection
    
    def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ) -> None:
        """
        Add documents to the collection
        
        Args:
            documents: List of document texts
            metadatas: Optional list of metadata dictionaries
            ids: Optional list of document IDs
        """
        try:
            # Generate IDs if not provided
            if ids is None:
                ids = [f"doc_{i}" for i in range(len(documents))]
            
            # Add default metadata if not provided
            if metadatas is None:
                metadatas = [{"source": "onelens"} for _ in documents]
            
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Added {len(documents)} documents to ChromaDB collection")
            
        except Exception as e:
            logger.error(f"Error adding documents to ChromaDB: {e}")
            raise
    
    def query_documents(
        self,
        query_texts: Union[str, List[str]],
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
        include: List[str] = None
    ) -> Dict[str, Any]:
        """
        Query documents from the collection
        
        Args:
            query_texts: Query text(s)
            n_results: Number of results to return
            where: Optional metadata filter
            include: What to include in results (documents, metadatas, distances)
            
        Returns:
            Query results
        """
        try:
            if isinstance(query_texts, str):
                query_texts = [query_texts]
            
            if include is None:
                include = ["documents", "metadatas", "distances"]
            
            results = self.collection.query(
                query_texts=query_texts,
                n_results=n_results,
                where=where,
                include=include
            )
            
            logger.info(f"Queried ChromaDB with {len(query_texts)} queries, got {len(results.get('documents', []))} result sets")
            return results
            
        except Exception as e:
            logger.error(f"Error querying ChromaDB: {e}")
            raise
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the collection"""
        try:
            count = self.collection.count()
            return {
                "name": self.collection_name,
                "count": count,
                "metadata": self.collection.metadata
            }
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {"error": str(e)}
    
    def delete_collection(self) -> bool:
        """Delete the collection"""
        try:
            self.client.delete_collection(name=self.collection_name)
            self._collection = None
            logger.info(f"Deleted ChromaDB collection: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting collection: {e}")
            return False
    
    def reset_collection(self) -> bool:
        """Reset (clear) the collection"""
        try:
            # Delete and recreate the collection
            self.delete_collection()
            self._collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "OneLens knowledge base"}
            )
            logger.info(f"Reset ChromaDB collection: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"Error resetting collection: {e}")
            return False
    
    def update_documents(
        self,
        ids: List[str],
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """Update existing documents"""
        try:
            self.collection.update(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            logger.info(f"Updated {len(ids)} documents in ChromaDB collection")
        except Exception as e:
            logger.error(f"Error updating documents: {e}")
            raise
    
    def delete_documents(self, ids: List[str]) -> None:
        """Delete documents by IDs"""
        try:
            self.collection.delete(ids=ids)
            logger.info(f"Deleted {len(ids)} documents from ChromaDB collection")
        except Exception as e:
            logger.error(f"Error deleting documents: {e}")
            raise
    
    def list_collections(self) -> List[str]:
        """List all collections in the database"""
        try:
            collections = self.client.list_collections()
            return [col.name for col in collections]
        except Exception as e:
            logger.error(f"Error listing collections: {e}")
            return []

# Global instance
chromadb_service = ChromaDBService()
