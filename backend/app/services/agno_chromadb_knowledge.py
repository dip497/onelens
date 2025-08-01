from typing import List, Dict, Any, Optional, Union
import logging
from agno.agent import AgentKnowledge
from agno.document.base import Document

from app.services.chromadb_service import ChromaDBService
from app.core.config import settings

logger = logging.getLogger(__name__)

class ChromaDBKnowledge(AgentKnowledge):
    """
    Agno-compatible knowledge base that uses ChromaDB as the backend
    """
    
    def __init__(
        self,
        chromadb_service: ChromaDBService = None,
        collection_name: str = None,
        **kwargs
    ):
        # Initialize the parent class
        super().__init__(**kwargs)
        
        # Initialize ChromaDB service
        self.chromadb_service = chromadb_service or ChromaDBService(
            collection_name=collection_name or settings.CHROMA_COLLECTION_NAME
        )
        
        # Store configuration
        self.collection_name = collection_name or settings.CHROMA_COLLECTION_NAME
        
        logger.info(f"Initialized ChromaDBKnowledge with collection: {self.collection_name}")
    
    def load_text(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Load a single text document into the knowledge base
        
        Args:
            text: The text content to add
            metadata: Optional metadata for the document
        """
        try:
            # Generate a unique ID for this document
            doc_id = f"text_{hash(text)}"
            
            # Prepare metadata
            doc_metadata = metadata or {}
            doc_metadata.update({
                "source": "text_input",
                "type": "text"
            })
            
            # Add to ChromaDB
            self.chromadb_service.add_documents(
                documents=[text],
                metadatas=[doc_metadata],
                ids=[doc_id]
            )
            
            logger.info(f"Loaded text document into knowledge base: {doc_id}")
            
        except Exception as e:
            logger.error(f"Error loading text into knowledge base: {e}")
            raise
    
    def load_documents(self, documents: List[Document]) -> None:
        """
        Load multiple documents into the knowledge base
        
        Args:
            documents: List of Document objects to add
        """
        try:
            texts = []
            metadatas = []
            ids = []
            
            for i, doc in enumerate(documents):
                # Extract text content
                text = doc.content if hasattr(doc, 'content') else str(doc)
                texts.append(text)
                
                # Prepare metadata
                metadata = getattr(doc, 'metadata', {}) or {}
                metadata.update({
                    "source": "document_input",
                    "type": "document",
                    "doc_index": i
                })
                metadatas.append(metadata)
                
                # Generate ID
                doc_id = getattr(doc, 'id', None) or f"doc_{i}_{hash(text)}"
                ids.append(str(doc_id))
            
            # Add all documents to ChromaDB
            self.chromadb_service.add_documents(
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )
            
            logger.info(f"Loaded {len(documents)} documents into knowledge base")
            
        except Exception as e:
            logger.error(f"Error loading documents into knowledge base: {e}")
            raise
    
    def search(
        self,
        query: str,
        num_documents: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        Search the knowledge base for relevant documents
        
        Args:
            query: Search query
            num_documents: Number of documents to return
            filters: Optional metadata filters
            
        Returns:
            List of relevant Document objects
        """
        try:
            # Query ChromaDB
            results = self.chromadb_service.query_documents(
                query_texts=query,
                n_results=num_documents,
                where=filters,
                include=["documents", "metadatas", "distances"]
            )
            
            # Convert results to Document objects
            documents = []
            if results.get("documents") and len(results["documents"]) > 0:
                docs = results["documents"][0]  # First query results
                metadatas = results.get("metadatas", [{}])[0] if results.get("metadatas") else [{}] * len(docs)
                distances = results.get("distances", [0])[0] if results.get("distances") else [0] * len(docs)
                
                for i, (doc_text, metadata, distance) in enumerate(zip(docs, metadatas, distances)):
                    # Add distance to metadata
                    metadata = metadata or {}
                    metadata["similarity_score"] = 1 - distance  # Convert distance to similarity
                    metadata["distance"] = distance
                    
                    # Create Document object
                    document = Document(
                        content=doc_text,
                        metadata=metadata
                    )
                    documents.append(document)
            
            logger.info(f"Found {len(documents)} documents for query: {query[:50]}...")
            return documents
            
        except Exception as e:
            logger.error(f"Error searching knowledge base: {e}")
            return []
    
    def exists(self) -> bool:
        """Check if the knowledge base exists and has content"""
        try:
            info = self.chromadb_service.get_collection_info()
            return info.get("count", 0) > 0
        except Exception:
            return False
    
    def delete(self) -> bool:
        """Delete the entire knowledge base"""
        try:
            return self.chromadb_service.delete_collection()
        except Exception as e:
            logger.error(f"Error deleting knowledge base: {e}")
            return False
    
    def clear(self) -> bool:
        """Clear all content from the knowledge base"""
        try:
            return self.chromadb_service.reset_collection()
        except Exception as e:
            logger.error(f"Error clearing knowledge base: {e}")
            return False
    
    def get_info(self) -> Dict[str, Any]:
        """Get information about the knowledge base"""
        return self.chromadb_service.get_collection_info()
    
    def add_from_database(
        self,
        query_func,
        text_field: str = "content",
        metadata_fields: List[str] = None,
        id_field: str = "id"
    ) -> int:
        """
        Add documents from database query results
        
        Args:
            query_func: Function that returns database query results
            text_field: Field name containing the text content
            metadata_fields: List of field names to include as metadata
            id_field: Field name to use as document ID
            
        Returns:
            Number of documents added
        """
        try:
            # Execute the query function
            results = query_func()
            
            if not results:
                logger.info("No results from database query")
                return 0
            
            texts = []
            metadatas = []
            ids = []
            
            metadata_fields = metadata_fields or []
            
            for result in results:
                # Extract text content
                if hasattr(result, text_field):
                    text = getattr(result, text_field)
                elif isinstance(result, dict):
                    text = result.get(text_field)
                else:
                    continue
                
                if not text:
                    continue
                
                texts.append(str(text))
                
                # Extract metadata
                metadata = {"source": "database"}
                for field in metadata_fields:
                    if hasattr(result, field):
                        metadata[field] = getattr(result, field)
                    elif isinstance(result, dict):
                        metadata[field] = result.get(field)
                
                metadatas.append(metadata)
                
                # Extract ID
                if hasattr(result, id_field):
                    doc_id = str(getattr(result, id_field))
                elif isinstance(result, dict):
                    doc_id = str(result.get(id_field, hash(text)))
                else:
                    doc_id = str(hash(text))
                
                ids.append(doc_id)
            
            # Add to ChromaDB
            if texts:
                self.chromadb_service.add_documents(
                    documents=texts,
                    metadatas=metadatas,
                    ids=ids
                )
            
            logger.info(f"Added {len(texts)} documents from database to knowledge base")
            return len(texts)
            
        except Exception as e:
            logger.error(f"Error adding documents from database: {e}")
            return 0
