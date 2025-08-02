"""
Test agno_service_v2 by hitting the API directly
"""
import requests
import json
import time

# API endpoint - adjust if needed
BASE_URL = "http://localhost:8000"

def test_feature_analysis():
    """Test feature analysis through API"""
    
    # Get an existing feature ID - using MFA feature
    feature_id = "e90f58ab-bad8-4f79-baf6-ffedf68405e2"  # Multi-Factor Authentication feature
    
    # Endpoint to trigger analysis
    url = f"{BASE_URL}/api/v1/features/{feature_id}/analyze"
    
    print(f"Testing feature analysis for ID: {feature_id}")
    print(f"URL: {url}")
    
    # Request different types of analysis
    analysis_requests = [
        {
            "name": "Trend Analysis Only",
            "payload": {
                "analysis_types": ["trend_analysis"]
            }
        },
        {
            "name": "Business Impact Only", 
            "payload": {
                "analysis_types": ["business_impact"]
            }
        },
        {
            "name": "All Analyses",
            "payload": {
                "analysis_types": [
                    "trend_analysis",
                    "business_impact", 
                    "competitive_analysis",
                    "geographic_analysis",
                    "priority_scoring"
                ]
            }
        }
    ]
    
    for test in analysis_requests:
        print(f"\n{'='*60}")
        print(f"Testing: {test['name']}")
        print(f"{'='*60}")
        
        try:
            response = requests.post(url, json=test['payload'])
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"Result: {json.dumps(result, indent=2)}")
                
                # Check if JSON mode is working
                if result.get("status") == "completed":
                    print("✅ Analysis completed successfully!")
                else:
                    print(f"⚠️  Analysis status: {result.get('status')}")
            else:
                print(f"❌ Error: {response.text}")
                
        except Exception as e:
            print(f"❌ Exception: {str(e)}")
            
        # Small delay between requests
        time.sleep(2)

def test_epic_analysis():
    """Test epic analysis through API"""
    
    # Get an existing epic ID - you may need to adjust this
    epic_id = "epic_01J663CQV69VSNG6ME3G5RD8SJ"  # Replace with actual epic ID
    
    url = f"{BASE_URL}/api/v1/epics/{epic_id}/analyze"
    
    print(f"\n{'='*60}")
    print(f"Testing epic analysis for ID: {epic_id}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    try:
        response = requests.post(url)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"Result: {json.dumps(result, indent=2)}")
        else:
            print(f"❌ Error: {response.text}")
            
    except Exception as e:
        print(f"❌ Exception: {str(e)}")

if __name__ == "__main__":
    print("Testing agno_service_v2 with JSON mode enabled")
    print("Make sure the backend server is running on http://localhost:8000")
    print("")
    
    # Test feature analysis
    test_feature_analysis()
    
    # Optionally test epic analysis
    # test_epic_analysis()