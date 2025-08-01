#!/usr/bin/env python3
"""
Script to initialize the ChromaDB knowledge base with OneLens data
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.services.knowledge_loader import knowledge_loader
from app.services.chromadb_service import chromadb_service
from app.services.agno_chromadb_knowledge import ChromaDBKnowledge

async def main():
    """Initialize the knowledge base"""
    print("🚀 Initializing OneLens Knowledge Base...")
    
    try:
        # Check if knowledge base already exists
        kb = ChromaDBKnowledge()
        if kb.exists():
            print("📚 Knowledge base already exists")
            info = kb.get_info()
            print(f"   Collection: {info.get('name')}")
            print(f"   Documents: {info.get('count', 0)}")
            
            # Ask if user wants to recreate
            response = input("\n🔄 Do you want to recreate the knowledge base? (y/N): ")
            recreate = response.lower().startswith('y')
        else:
            print("📚 Knowledge base does not exist, creating new one...")
            recreate = True
        
        # Load data into knowledge base
        print("\n📖 Loading OneLens data into knowledge base...")
        counts = await knowledge_loader.load_all_data(recreate=recreate)
        
        print("\n✅ Knowledge base initialization complete!")
        print("\n📊 Loaded data summary:")
        for data_type, count in counts.items():
            print(f"   {data_type}: {count}")
        
        total = sum(counts.values())
        print(f"\n📈 Total documents: {total}")
        
        # Test the knowledge base
        print("\n🔍 Testing knowledge base search...")
        test_queries = [
            "product management",
            "customer requests",
            "competitors",
            "features"
        ]
        
        for query in test_queries:
            results = kb.search(query, num_documents=3)
            print(f"\n   Query: '{query}' -> {len(results)} results")
            for i, doc in enumerate(results[:2], 1):
                content_preview = doc.content[:100] + "..." if len(doc.content) > 100 else doc.content
                print(f"     {i}. {content_preview}")
        
        print("\n🎉 Knowledge base is ready for use!")
        print("\n💡 You can now:")
        print("   - Use the OneLens AI Assistant with knowledge-based responses")
        print("   - Query the knowledge base via API endpoints")
        print("   - Add more data to the knowledge base as needed")
        
    except Exception as e:
        print(f"\n❌ Error initializing knowledge base: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
