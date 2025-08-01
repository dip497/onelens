#!/usr/bin/env python3
"""
Simple test script to verify ChromaDB and Agno knowledge integration
"""

import sys
import os
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

def test_chromadb_service():
    """Test ChromaDB service functionality"""
    print("🧪 Testing ChromaDB Service...")
    
    try:
        from app.services.chromadb_service import ChromaDBService
        
        # Create a test service with a different collection
        service = ChromaDBService(collection_name="test_collection")
        
        # Test adding documents
        test_docs = [
            "OneLens is a product management platform",
            "Features can be requested by customers",
            "Epics contain multiple features"
        ]
        
        test_metadata = [
            {"type": "platform", "category": "description"},
            {"type": "feature", "category": "process"},
            {"type": "epic", "category": "structure"}
        ]
        
        service.add_documents(
            documents=test_docs,
            metadatas=test_metadata,
            ids=["doc1", "doc2", "doc3"]
        )
        
        # Test querying
        results = service.query_documents(
            query_texts="product management",
            n_results=2
        )
        
        print(f"   ✅ Added {len(test_docs)} documents")
        print(f"   ✅ Query returned {len(results.get('documents', []))} result sets")
        
        # Clean up
        service.delete_collection()
        print("   ✅ Cleaned up test collection")
        
        return True
        
    except Exception as e:
        print(f"   ❌ ChromaDB Service test failed: {e}")
        return False

def test_agno_knowledge():
    """Test Agno knowledge integration"""
    print("\n🧪 Testing Agno Knowledge Integration...")
    
    try:
        from app.services.agno_chromadb_knowledge import ChromaDBKnowledge
        
        # Create a test knowledge base
        kb = ChromaDBKnowledge(collection_name="test_agno_kb")
        
        # Test loading text
        kb.load_text(
            text="OneLens helps product managers prioritize features based on customer feedback",
            metadata={"source": "test", "type": "description"}
        )
        
        # Test searching
        results = kb.search(query="product managers", num_documents=5)
        
        print(f"   ✅ Loaded text into knowledge base")
        print(f"   ✅ Search returned {len(results)} documents")
        
        if results:
            print(f"   ✅ First result: {results[0].content[:50]}...")
        
        # Clean up
        kb.delete()
        print("   ✅ Cleaned up test knowledge base")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Agno Knowledge test failed: {e}")
        return False

def test_configuration():
    """Test configuration loading"""
    print("\n🧪 Testing Configuration...")
    
    try:
        from app.core.config import settings
        
        print(f"   ✅ ChromaDB Path: {settings.CHROMA_DB_PATH}")
        print(f"   ✅ Collection Name: {settings.CHROMA_COLLECTION_NAME}")
        print(f"   ✅ Embedding Model: {settings.EMBEDDING_MODEL}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Configuration test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Testing OneLens Knowledge Base Integration\n")
    
    tests = [
        ("Configuration", test_configuration),
        ("ChromaDB Service", test_chromadb_service),
        ("Agno Knowledge", test_agno_knowledge)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"   ❌ {test_name} test crashed: {e}")
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Knowledge base integration is working correctly.")
        print("\n💡 Next steps:")
        print("   1. Run the initialization script: python scripts/init_knowledge_base.py")
        print("   2. Start the FastAPI server to test the API endpoints")
        print("   3. Try asking the AI assistant questions about your data")
    else:
        print("❌ Some tests failed. Please check the error messages above.")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
