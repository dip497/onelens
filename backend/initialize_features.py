#!/usr/bin/env python3
"""
Initialize predefined features through the existing API endpoints.
This script creates an epic and then adds the specified features with detailed descriptions.
"""

import asyncio
import httpx
import json
from typing import List, Dict, Any

# API base URL - adjust as needed
API_BASE_URL = "http://localhost:8000/api/v1"

# Feature definitions with detailed descriptions and metadata
FEATURES_TO_INITIALIZE = [
    {
        "title": "SCIM Integration",
        "description": """
        System for Cross-domain Identity Management (SCIM) integration enables automated user provisioning and deprovisioning across enterprise systems.
        
        Key capabilities:
        - Automated user lifecycle management
        - Real-time synchronization with identity providers (Azure AD, Okta, etc.)
        - Support for SCIM 2.0 protocol standards
        - Bulk user operations and group management
        - Audit logging for compliance requirements
        - Custom attribute mapping and transformation
        
        Business value:
        - Reduces manual IT overhead by 70-80%
        - Improves security through automated access control
        - Ensures compliance with enterprise identity policies
        - Accelerates employee onboarding/offboarding processes
        """
    },
    {
        "title": "Periodic User Workflow",
        "description": """
        Automated workflow system that executes recurring tasks and processes based on configurable schedules and triggers.
        
        Key capabilities:
        - Flexible scheduling (daily, weekly, monthly, custom intervals)
        - Conditional workflow execution based on system state
        - Multi-step workflow orchestration with error handling
        - Integration with external systems and APIs
        - Real-time monitoring and alerting
        - Workflow versioning and rollback capabilities
        
        Use cases:
        - Regular system maintenance tasks
        - Periodic data synchronization
        - Automated reporting and notifications
        - Compliance checks and audits
        - Resource cleanup and optimization
        
        Business value:
        - Reduces operational overhead through automation
        - Ensures consistent execution of critical processes
        - Improves system reliability and performance
        - Enables proactive system management
        """
    },
    {
        "title": "Service-based Architecture",
        "description": """
        Microservices architecture implementation that enables scalable, maintainable, and resilient system design.
        
        Key capabilities:
        - Modular service decomposition
        - API-first design with RESTful interfaces
        - Service discovery and load balancing
        - Distributed configuration management
        - Circuit breaker patterns for fault tolerance
        - Centralized logging and monitoring
        - Container orchestration support
        
        Technical benefits:
        - Independent service deployment and scaling
        - Technology stack flexibility per service
        - Improved fault isolation and recovery
        - Enhanced development team autonomy
        - Better resource utilization
        
        Business value:
        - Faster time-to-market for new features
        - Improved system reliability and uptime
        - Reduced technical debt and maintenance costs
        - Enhanced ability to scale with business growth
        """
    },
    {
        "title": "RDP for Unmanaged Devices (Co-browsing for Agentless Remote)",
        "description": """
        Remote Desktop Protocol implementation for unmanaged devices with co-browsing capabilities, enabling secure remote access without requiring agent installation.
        
        Key capabilities:
        - Browser-based remote desktop access
        - Real-time screen sharing and co-browsing
        - Multi-platform support (Windows, Mac, Linux, mobile)
        - Session recording and playback
        - File transfer capabilities
        - Multi-monitor support
        - Bandwidth optimization and compression
        
        Security features:
        - End-to-end encryption
        - Session-based authentication
        - Access control and permissions
        - Audit trail and compliance logging
        - Network isolation and tunneling
        
        Use cases:
        - Remote technical support
        - Employee assistance and training
        - System administration and maintenance
        - Collaborative troubleshooting
        - Secure access to corporate resources
        
        Business value:
        - Reduces support costs and resolution time
        - Enables remote work capabilities
        - Improves customer satisfaction
        - Eliminates need for on-site visits
        """
    },
    {
        "title": "Minor/Major OS Patch Update",
        "description": """
        Comprehensive operating system patch management system that automates the deployment of security updates and system patches across enterprise environments.
        
        Key capabilities:
        - Automated patch detection and classification
        - Risk assessment and impact analysis
        - Staged deployment with rollback capabilities
        - Maintenance window scheduling
        - Pre and post-patch validation
        - Compliance reporting and tracking
        - Integration with WSUS, SCCM, and third-party tools
        
        Patch categories:
        - Critical security patches (immediate deployment)
        - Important updates (scheduled deployment)
        - Optional updates (user-controlled)
        - Driver and firmware updates
        - Application patches and updates
        
        Features:
        - Bandwidth throttling and optimization
        - Offline patch deployment
        - Custom patch approval workflows
        - Automated testing in sandbox environments
        - Detailed reporting and analytics
        
        Business value:
        - Reduces security vulnerabilities by 95%+
        - Ensures regulatory compliance
        - Minimizes system downtime
        - Reduces IT administrative overhead
        - Improves overall system stability
        """
    },
    {
        "title": "Discovery of Portable Applications",
        "description": """
        Advanced application discovery system that identifies and catalogs portable applications across the enterprise network, providing visibility into software usage and compliance.
        
        Key capabilities:
        - Network-wide application scanning
        - Portable app signature detection
        - Real-time monitoring and alerting
        - Software inventory management
        - License compliance tracking
        - Usage analytics and reporting
        - Integration with asset management systems
        
        Detection methods:
        - File system scanning and analysis
        - Process monitoring and identification
        - Network traffic analysis
        - Registry and configuration analysis
        - Behavioral pattern recognition
        
        Supported app types:
        - Portable executables (.exe, .app)
        - Browser-based applications
        - Virtualized applications
        - Cloud-based software
        - Custom and in-house applications
        
        Security features:
        - Malware and threat detection
        - Unauthorized software identification
        - Policy enforcement and blocking
        - Quarantine and remediation
        
        Business value:
        - Improves software license compliance
        - Reduces security risks from unauthorized software
        - Provides complete software asset visibility
        - Enables data-driven software procurement decisions
        - Supports regulatory audit requirements
        """
    }
]

async def create_epic() -> str:
    """Create an epic to contain the features."""
    epic_data = {
        "title": "Core Platform Features Initiative",
        "description": "Epic containing essential platform features for enterprise IT management and remote access capabilities",
        "business_justification": "These features are critical for providing comprehensive IT management, security, and remote access capabilities that meet enterprise customer requirements and competitive positioning."
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE_URL}/epics",
            json=epic_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 201:
            epic = response.json()
            print(f"✅ Created epic: {epic['title']} (ID: {epic['id']})")
            return epic['id']
        else:
            print(f"❌ Failed to create epic: {response.status_code} - {response.text}")
            raise Exception(f"Failed to create epic: {response.status_code}")

async def create_feature(epic_id: str, feature_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a single feature using the existing API endpoint."""
    payload = {
        "epic_id": epic_id,
        "title": feature_data["title"],
        "description": feature_data["description"]
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE_URL}/features",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 201:
            feature = response.json()
            print(f"✅ Created feature: {feature['title']} (ID: {feature['id']})")
            return feature
        else:
            print(f"❌ Failed to create feature '{feature_data['title']}': {response.status_code} - {response.text}")
            raise Exception(f"Failed to create feature: {response.status_code}")

async def initialize_features():
    """Main function to initialize all features."""
    print("🚀 Starting feature initialization...")
    print(f"📊 Will create {len(FEATURES_TO_INITIALIZE)} features")
    print("-" * 60)
    
    try:
        # Step 1: Create the epic
        print("📝 Creating epic...")
        epic_id = await create_epic()
        print()
        
        # Step 2: Create all features
        print("🔧 Creating features...")
        created_features = []
        
        for i, feature_data in enumerate(FEATURES_TO_INITIALIZE, 1):
            print(f"[{i}/{len(FEATURES_TO_INITIALIZE)}] Creating: {feature_data['title']}")
            feature = await create_feature(epic_id, feature_data)
            created_features.append(feature)
            print()
        
        # Step 3: Summary
        print("=" * 60)
        print("🎉 Feature initialization completed successfully!")
        print(f"📈 Epic ID: {epic_id}")
        print(f"📊 Features created: {len(created_features)}")
        print()
        print("📋 Created features:")
        for feature in created_features:
            print(f"  • {feature['title']} (ID: {feature['id']})")
        
        print()
        print("🔗 Next steps:")
        print("  1. Access the features through the web interface")
        print("  2. Run analysis on individual features as needed")
        print("  3. Add feature requests from customers")
        print("  4. Configure priority scoring")
        
        return {
            "epic_id": epic_id,
            "features": created_features,
            "message": f"Successfully initialized {len(created_features)} features"
        }
        
    except Exception as e:
        print(f"💥 Error during initialization: {str(e)}")
        raise

async def main():
    """Entry point for the script."""
    try:
        result = await initialize_features()
        print(f"\n✨ Initialization complete: {result['message']}")
    except Exception as e:
        print(f"\n💥 Initialization failed: {str(e)}")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())
