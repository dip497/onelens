#!/usr/bin/env python3
"""
Test all API endpoints to ensure they're working properly.
"""

import asyncio
import aiohttp
import json
from typing import Dict, Any

BASE_URL = "http://localhost:8000/api/v1"

async def test_endpoint(session: aiohttp.ClientSession, method: str, path: str, data: Dict[str, Any] = None) -> tuple[bool, str]:
    """Test a single endpoint and return success status and message."""
    try:
        url = f"{BASE_URL}{path}"
        
        if method == "GET":
            async with session.get(url) as resp:
                if resp.status < 400:
                    return True, f"✅ {method} {path}: {resp.status}"
                else:
                    text = await resp.text()
                    return False, f"❌ {method} {path}: {resp.status} - {text[:100]}"
        
        elif method == "POST":
            async with session.post(url, json=data) as resp:
                if resp.status < 400:
                    return True, f"✅ {method} {path}: {resp.status}"
                else:
                    text = await resp.text()
                    return False, f"❌ {method} {path}: {resp.status} - {text[:100]}"
                    
    except Exception as e:
        return False, f"❌ {method} {path}: Error - {str(e)}"

async def test_all_apis():
    """Test all API endpoints."""
    print("🧪 Testing All API Endpoints\n")
    
    async with aiohttp.ClientSession() as session:
        tests = []
        
        # 1. Persona/Product APIs
        tests.append(("GET", "/persona/", None))
        tests.append(("GET", "/persona/stats", None))
        
        # 2. Epic APIs
        tests.append(("GET", "/epics", None))
        tests.append(("POST", "/epics", {
            "title": "Test Epic",
            "description": "Test Description",
            "business_justification": "Business value"
        }))
        
        # 3. Feature APIs
        tests.append(("GET", "/features/", None))
        
        # 4. Customer APIs
        tests.append(("GET", "/customers/", None))
        tests.append(("POST", "/customers/", {
            "name": "Test Customer",
            "email": "test@example.com",
            "company": "Test Corp"
        }))
        
        # 5. Competitor APIs
        tests.append(("GET", "/competitors/", None))
        tests.append(("POST", "/competitors/", {
            "name": "Test Competitor",
            "website": "https://competitor.com",
            "description": "Test competitor"
        }))
        
        # 6. Product APIs
        tests.append(("GET", "/products/", None))
        
        # 7. Module Feature APIs
        tests.append(("GET", "/module-features/", None))
        
        # 8. Battle Card APIs
        tests.append(("GET", "/battle-cards/", None))
        
        # 9. RFP APIs
        tests.append(("GET", "/rfp/", None))
        
        # 10. Agent APIs
        tests.append(("GET", "/agent/status", None))
        
        # Run all tests
        results = []
        for method, path, data in tests:
            success, message = await test_endpoint(session, method, path, data)
            results.append((success, message))
            print(message)
        
        # Summary
        success_count = sum(1 for s, _ in results if s)
        total_count = len(results)
        
        print(f"\n📊 Summary: {success_count}/{total_count} endpoints working")
        
        if success_count < total_count:
            print("\n❌ Failed endpoints need attention:")
            for success, message in results:
                if not success:
                    print(f"  {message}")

async def test_epic_features():
    """Test epic feature creation specifically."""
    print("\n🧪 Testing Epic Feature Creation\n")
    
    async with aiohttp.ClientSession() as session:
        # First create an epic
        async with session.post(f"{BASE_URL}/epics", json={
            "title": "Test Epic for Features",
            "description": "Testing feature creation",
            "business_justification": "Testing"
        }) as resp:
            if resp.status == 201:
                epic_data = await resp.json()
                epic_id = epic_data["id"]
                print(f"✅ Created epic: {epic_id}")
                
                # Now create a feature in the epic
                async with session.post(f"{BASE_URL}/epics/{epic_id}/features", json={
                    "title": "Test Feature",
                    "description": "Feature created via epic endpoint"
                }) as feat_resp:
                    if feat_resp.status == 201:
                        feature_data = await feat_resp.json()
                        print(f"✅ Created feature in epic: {feature_data['id']}")
                    else:
                        text = await feat_resp.text()
                        print(f"❌ Failed to create feature: {feat_resp.status} - {text}")
                
                # Get features for the epic
                async with session.get(f"{BASE_URL}/epics/{epic_id}/features") as list_resp:
                    if list_resp.status == 200:
                        features = await list_resp.json()
                        print(f"✅ Retrieved {len(features)} features from epic")
                    else:
                        print(f"❌ Failed to get features: {list_resp.status}")
            else:
                print(f"❌ Failed to create epic: {resp.status}")

if __name__ == "__main__":
    asyncio.run(test_all_apis())
    asyncio.run(test_epic_features())