from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
import logging

from app.services.chromadb_service import chromadb_service
from app.services.knowledge_loader import knowledge_loader
from app.services.agno_chromadb_knowledge import ChromaDBKnowledge

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/info")
async def get_knowledge_base_info() -> Dict[str, Any]:
    """Get information about the knowledge base"""
    try:
        info = chromadb_service.get_collection_info()
        return {
            "status": "success",
            "data": info
        }
    except Exception as e:
        logger.error(f"Error getting knowledge base info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/load")
async def load_knowledge_base(recreate: bool = Query(False, description="Whether to recreate the knowledge base")) -> Dict[str, Any]:
    """Load all OneLens data into the knowledge base"""
    try:
        logger.info(f"Loading knowledge base (recreate={recreate})")
        counts = await knowledge_loader.load_all_data(recreate=recreate)
        
        return {
            "status": "success",
            "message": "Knowledge base loaded successfully",
            "data": {
                "counts": counts,
                "total_loaded": sum(counts.values())
            }
        }
    except Exception as e:
        logger.error(f"Error loading knowledge base: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clear")
async def clear_knowledge_base() -> Dict[str, Any]:
    """Clear all content from the knowledge base"""
    try:
        success = chromadb_service.reset_collection()
        if success:
            return {
                "status": "success",
                "message": "Knowledge base cleared successfully"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to clear knowledge base")
    except Exception as e:
        logger.error(f"Error clearing knowledge base: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/")
async def delete_knowledge_base() -> Dict[str, Any]:
    """Delete the entire knowledge base"""
    try:
        success = chromadb_service.delete_collection()
        if success:
            return {
                "status": "success",
                "message": "Knowledge base deleted successfully"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to delete knowledge base")
    except Exception as e:
        logger.error(f"Error deleting knowledge base: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search")
async def search_knowledge_base(
    query: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Number of results to return"),
    filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Search the knowledge base"""
    try:
        # Create knowledge base instance for searching
        kb = ChromaDBKnowledge()
        documents = kb.search(query=query, num_documents=limit, filters=filters)
        
        # Convert documents to serializable format
        results = []
        for doc in documents:
            result = {
                "content": doc.content,
                "metadata": doc.metadata
            }
            results.append(result)
        
        return {
            "status": "success",
            "data": {
                "query": query,
                "results": results,
                "count": len(results)
            }
        }
    except Exception as e:
        logger.error(f"Error searching knowledge base: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/add-text")
async def add_text_to_knowledge_base(
    text: str = Query(..., description="Text to add to knowledge base"),
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Add a text document to the knowledge base"""
    try:
        kb = ChromaDBKnowledge()
        kb.load_text(text=text, metadata=metadata)
        
        return {
            "status": "success",
            "message": "Text added to knowledge base successfully",
            "data": {
                "text_length": len(text),
                "metadata": metadata
            }
        }
    except Exception as e:
        logger.error(f"Error adding text to knowledge base: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/collections")
async def list_collections() -> Dict[str, Any]:
    """List all ChromaDB collections"""
    try:
        collections = chromadb_service.list_collections()
        return {
            "status": "success",
            "data": {
                "collections": collections,
                "count": len(collections)
            }
        }
    except Exception as e:
        logger.error(f"Error listing collections: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def knowledge_base_health() -> Dict[str, Any]:
    """Check the health of the knowledge base"""
    try:
        # Check if knowledge base exists and has content
        kb = ChromaDBKnowledge()
        exists = kb.exists()
        info = kb.get_info()
        
        return {
            "status": "success",
            "data": {
                "exists": exists,
                "healthy": exists and info.get("count", 0) > 0,
                "info": info
            }
        }
    except Exception as e:
        logger.error(f"Error checking knowledge base health: {e}")
        return {
            "status": "error",
            "data": {
                "exists": False,
                "healthy": False,
                "error": str(e)
            }
        }
