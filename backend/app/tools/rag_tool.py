"""RAG Tool for OneLens Knowledge Base Search"""

import os
import openai
import chromadb
from pathlib import Path
from typing import List
from dataclasses import dataclass
from agno.tools import tool


@dataclass
class SearchResult:
    """Search result data structure"""
    title: str
    url: str
    content: str
    similarity_score: float
    content_length: int


class RAGQueryInterface:
    """ChromaDB query interface"""

    def __init__(self, openai_api_key: str, collection_name: str = "crawl_results_documents"):
        self.openai_client = openai.OpenAI(api_key=openai_api_key)
        chroma_db_path = Path(__file__).parent.parent.parent.parent / "chroma_db"
        self.client = chromadb.PersistentClient(path=str(chroma_db_path))
        self.collection = self.client.get_collection(name=collection_name)

    def get_openai_embedding(self, text: str) -> List[float]:
        """Get embedding from OpenAI API"""
        try:
            if len(text) > 32000:  # Truncate if too long
                text = text[:32000]

            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            return response.data[0].embedding
        except Exception:
            return []

    def search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """Search the vector database"""
        try:
            query_embedding = self.get_openai_embedding(query)
            if not query_embedding:
                return []

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, 50),
                include=['documents', 'metadatas', 'distances']
            )

            search_results = []
            documents = results.get('documents', [[]])[0]
            metadatas = results.get('metadatas', [[]])[0]
            distances = results.get('distances', [[]])[0]

            for doc, metadata, distance in zip(documents, metadatas, distances):
                search_result = SearchResult(
                    title=metadata.get('title', 'No Title'),
                    url=metadata.get('url', 'No URL'),
                    content=doc,
                    similarity_score=1 - distance,
                    content_length=metadata.get('content_length', len(doc))
                )
                search_results.append(search_result)

            return search_results
        except Exception:
            return []


# Global RAG interface
_rag_interface = None


def get_rag_interface():
    """Get or create RAG interface"""
    global _rag_interface
    if _rag_interface is None:
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        _rag_interface = RAGQueryInterface(
            openai_api_key=openai_api_key,
            collection_name="crawl_results_documents"
        )
    return _rag_interface


@tool(show_result=False)
def search_knowledge_base(query: str, max_results: int = 1) -> str:
    """
    Search the OneLens ChromaDB knowledge base for relevant information.
    Only returns results with confidence score > 60% to ensure high-quality responses.

    Args:
        query: The search query to find relevant documents
        max_results: Maximum number of results to return (not used, always returns top 2)

    Returns:
        str: Formatted context from ChromaDB with source links, or message if confidence too low
    """
    try:
        print("ChromaDB Query Input:", query)
        rag_interface = get_rag_interface()

        # Always retrieve top 2 chunks as specified
        search_results = rag_interface.search(query, top_k=2)

        if not search_results:
            return "No relevant information found in the ChromaDB knowledge base."

        # Filter results with confidence score > 60% (0.6)
        high_confidence_results = []
        for result in search_results:
            confidence_percentage = result.similarity_score * 100
            print(f"ChromaDB Chunk Confidence: {confidence_percentage:.1f}%")

            if result.similarity_score > 0.6:  # 60% confidence threshold
                high_confidence_results.append(result)

        # Only proceed if we have high-confidence results
        if not high_confidence_results:
            return "No high-confidence information found in ChromaDB (confidence < 60%). Cannot provide reliable answer from knowledge base."

        # Format high-confidence results only
        context_parts = []
        source_links = []

        for i, result in enumerate(high_confidence_results):
            confidence_percentage = result.similarity_score * 100
            context_parts.append(f"Document {i+1} (Confidence: {confidence_percentage:.1f}%): {result.content}")
            context_parts.append(f"Title: {result.title}")
            if result.url and result.url != "No URL":
                context_parts.append(f"Source URL: {result.url}")
                if result.url not in source_links:
                    source_links.append(result.url)
            context_parts.append("---")

        context_data = "\n".join(context_parts)

        # Add source links
        if source_links:
            links_text = "\n\nCHROMADB SOURCE LINKS:\n" + "\n".join([f"- {link}" for link in source_links])
            context_data += links_text

        print("ChromaDB Output:", context_data)
        return context_data

    except Exception as e:
        print(f"ChromaDB Error: {e}")
        return "Error occurred while searching the ChromaDB knowledge base."
