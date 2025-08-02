"""
Feature Initializer Module
Provides functions to initialize predefined features through existing API endpoints.
Can be used as a standalone script or imported as a module.
"""

import requests
import json
from typing import List, Dict, Any, Optional

class FeatureInitializer:
    """Class to handle feature initialization through API calls."""
    
    def __init__(self, api_base_url: str = "http://localhost:8000/api/v1"):
        self.api_base_url = api_base_url
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def get_predefined_features(self) -> List[Dict[str, Any]]:
        """Get the list of predefined features to initialize."""
        return [
            {
                "title": "SCIM Integration",
                "description": """System for Cross-domain Identity Management (SCIM) integration enables automated user provisioning and deprovisioning across enterprise systems.

Key capabilities:
• Automated user lifecycle management
• Real-time synchronization with identity providers (Azure AD, Okta, etc.)
• Support for SCIM 2.0 protocol standards
• Bulk user operations and group management
• Audit logging for compliance requirements
• Custom attribute mapping and transformation

Business value:
• Reduces manual IT overhead by 70-80%
• Improves security through automated access control
• Ensures compliance with enterprise identity policies
• Accelerates employee onboarding/offboarding processes""",
                "category": "Identity Management",
                "complexity": "High",
                "target_segment": "Enterprise"
            },
            {
                "title": "Periodic User Workflow",
                "description": """Automated workflow system that executes recurring tasks and processes based on configurable schedules and triggers.

Key capabilities:
• Flexible scheduling (daily, weekly, monthly, custom intervals)
• Conditional workflow execution based on system state
• Multi-step workflow orchestration with error handling
• Integration with external systems and APIs
• Real-time monitoring and alerting
• Workflow versioning and rollback capabilities

Use cases:
• Regular system maintenance tasks
• Periodic data synchronization
• Automated reporting and notifications
• Compliance checks and audits
• Resource cleanup and optimization""",
                "category": "Automation",
                "complexity": "Medium",
                "target_segment": "All"
            },
            {
                "title": "Service-based Architecture",
                "description": """Microservices architecture implementation that enables scalable, maintainable, and resilient system design.

Key capabilities:
• Modular service decomposition
• API-first design with RESTful interfaces
• Service discovery and load balancing
• Distributed configuration management
• Circuit breaker patterns for fault tolerance
• Centralized logging and monitoring
• Container orchestration support

Business value:
• Faster time-to-market for new features
• Improved system reliability and uptime
• Reduced technical debt and maintenance costs
• Enhanced ability to scale with business growth""",
                "category": "Architecture",
                "complexity": "High",
                "target_segment": "Enterprise"
            },
            {
                "title": "RDP for Unmanaged Devices (Co-browsing for Agentless Remote)",
                "description": """Remote Desktop Protocol implementation for unmanaged devices with co-browsing capabilities, enabling secure remote access without requiring agent installation.

Key capabilities:
• Browser-based remote desktop access
• Real-time screen sharing and co-browsing
• Multi-platform support (Windows, Mac, Linux, mobile)
• Session recording and playback
• File transfer capabilities
• Multi-monitor support
• Bandwidth optimization and compression

Security features:
• End-to-end encryption
• Session-based authentication
• Access control and permissions
• Audit trail and compliance logging

Use cases:
• Remote technical support
• Employee assistance and training
• System administration and maintenance
• Collaborative troubleshooting""",
                "category": "Remote Access",
                "complexity": "High",
                "target_segment": "All"
            },
            {
                "title": "Minor/Major OS Patch Update",
                "description": """Comprehensive operating system patch management system that automates the deployment of security updates and system patches across enterprise environments.

Key capabilities:
• Automated patch detection and classification
• Risk assessment and impact analysis
• Staged deployment with rollback capabilities
• Maintenance window scheduling
• Pre and post-patch validation
• Compliance reporting and tracking
• Integration with WSUS, SCCM, and third-party tools

Patch categories:
• Critical security patches (immediate deployment)
• Important updates (scheduled deployment)
• Optional updates (user-controlled)
• Driver and firmware updates
• Application patches and updates

Business value:
• Reduces security vulnerabilities by 95%+
• Ensures regulatory compliance
• Minimizes system downtime
• Reduces IT administrative overhead""",
                "category": "Patch Management",
                "complexity": "Medium",
                "target_segment": "All"
            },
            {
                "title": "Discovery of Portable Applications",
                "description": """Advanced application discovery system that identifies and catalogs portable applications across the enterprise network, providing visibility into software usage and compliance.

Key capabilities:
• Network-wide application scanning
• Portable app signature detection
• Real-time monitoring and alerting
• Software inventory management
• License compliance tracking
• Usage analytics and reporting
• Integration with asset management systems

Detection methods:
• File system scanning and analysis
• Process monitoring and identification
• Network traffic analysis
• Registry and configuration analysis
• Behavioral pattern recognition

Security features:
• Malware and threat detection
• Unauthorized software identification
• Policy enforcement and blocking
• Quarantine and remediation

Business value:
• Improves software license compliance
• Reduces security risks from unauthorized software
• Provides complete software asset visibility
• Enables data-driven software procurement decisions""",
                "category": "Asset Management",
                "complexity": "Medium",
                "target_segment": "Enterprise"
            }
        ]
    
    def create_epic(self, title: str = None, description: str = None, business_justification: str = None) -> Dict[str, Any]:
        """Create an epic to contain the features."""
        epic_data = {
            "title": title or "Core Platform Features Initiative",
            "description": description or "Epic containing essential platform features for enterprise IT management and remote access capabilities",
            "business_justification": business_justification or "These features are critical for providing comprehensive IT management, security, and remote access capabilities that meet enterprise customer requirements and competitive positioning."
        }
        
        response = self.session.post(f"{self.api_base_url}/epics", json=epic_data)
        
        if response.status_code == 201:
            epic = response.json()
            print(f"✅ Created epic: {epic['title']} (ID: {epic['id']})")
            return epic
        else:
            print(f"❌ Failed to create epic: {response.status_code} - {response.text}")
            response.raise_for_status()
    
    def create_feature(self, epic_id: str, feature_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a single feature using the existing API endpoint."""
        payload = {
            "epic_id": epic_id,
            "title": feature_data["title"],
            "description": feature_data["description"]
        }
        
        response = self.session.post(f"{self.api_base_url}/features", json=payload)
        
        if response.status_code == 201:
            feature = response.json()
            print(f"✅ Created feature: {feature['title']} (ID: {feature['id']})")
            return feature
        else:
            print(f"❌ Failed to create feature '{feature_data['title']}': {response.status_code} - {response.text}")
            response.raise_for_status()
    
    def initialize_all_features(self, epic_title: str = None) -> Dict[str, Any]:
        """Initialize all predefined features."""
        print("🚀 Starting feature initialization...")
        
        # Create epic
        epic = self.create_epic(title=epic_title)
        epic_id = epic['id']
        
        # Get predefined features
        features_to_create = self.get_predefined_features()
        print(f"📊 Will create {len(features_to_create)} features")
        
        # Create features
        created_features = []
        for i, feature_data in enumerate(features_to_create, 1):
            print(f"[{i}/{len(features_to_create)}] Creating: {feature_data['title']}")
            feature = self.create_feature(epic_id, feature_data)
            created_features.append(feature)
        
        result = {
            "epic": epic,
            "features": created_features,
            "message": f"Successfully initialized {len(created_features)} features"
        }
        
        print("🎉 Feature initialization completed successfully!")
        print(f"📈 Epic ID: {epic_id}")
        print(f"📊 Features created: {len(created_features)}")
        
        return result
    
    def list_features(self, epic_id: str = None) -> List[Dict[str, Any]]:
        """List existing features, optionally filtered by epic."""
        params = {}
        if epic_id:
            params['epic_id'] = epic_id
        
        response = self.session.get(f"{self.api_base_url}/features", params=params)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('items', [])
        else:
            print(f"❌ Failed to list features: {response.status_code} - {response.text}")
            response.raise_for_status()
    
    def get_feature_details(self, feature_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific feature."""
        response = self.session.get(f"{self.api_base_url}/features/{feature_id}")
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Failed to get feature details: {response.status_code} - {response.text}")
            response.raise_for_status()

def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Initialize predefined features through API")
    parser.add_argument("--api-url", default="http://localhost:8000/api/v1", help="API base URL")
    parser.add_argument("--epic-title", help="Custom epic title")
    parser.add_argument("--list-only", action="store_true", help="Only list existing features")
    
    args = parser.parse_args()
    
    initializer = FeatureInitializer(args.api_url)
    
    if args.list_only:
        features = initializer.list_features()
        print(f"Found {len(features)} existing features:")
        for feature in features:
            print(f"  • {feature['title']} (ID: {feature['id']})")
    else:
        result = initializer.initialize_all_features(args.epic_title)
        print(f"\n✨ {result['message']}")

if __name__ == "__main__":
    main()
