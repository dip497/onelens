# Feature Initialization Guide

This guide explains how to initialize predefined features through the existing API endpoints.

## Overview

The feature initialization system provides two scripts to create a comprehensive set of predefined features:

1. **SCIM Integration** - Identity management and user provisioning
2. **Periodic User Workflow** - Automated recurring task execution
3. **Service-based Architecture** - Microservices implementation
4. **RDP for Unmanaged Devices** - Agentless remote access and co-browsing
5. **Minor/Major OS Patch Update** - Comprehensive patch management
6. **Discovery of Portable Applications** - Application discovery and compliance

## Files

- `initialize_features.py` - Async script for feature initialization
- `feature_initializer.py` - Synchronous module with CLI support
- `README_feature_initialization.md` - This documentation

## Usage

### Method 1: Using the Async Script

```bash
# Make sure the backend server is running
cd backend
python initialize_features.py
```

### Method 2: Using the Synchronous Module

```bash
# Initialize all features
python feature_initializer.py

# Use custom API URL
python feature_initializer.py --api-url http://localhost:8080/api/v1

# Use custom epic title
python feature_initializer.py --epic-title "My Custom Epic"

# List existing features only
python feature_initializer.py --list-only
```

### Method 3: Using as a Python Module

```python
from feature_initializer import FeatureInitializer

# Initialize the client
initializer = FeatureInitializer("http://localhost:8000/api/v1")

# Initialize all features
result = initializer.initialize_all_features()

# List existing features
features = initializer.list_features()

# Get specific feature details
feature = initializer.get_feature_details(feature_id)
```

## API Endpoints Used

The scripts use the existing API endpoints:

- `POST /api/v1/epics` - Create epic to contain features
- `POST /api/v1/features` - Create individual features
- `GET /api/v1/features` - List existing features
- `GET /api/v1/features/{id}` - Get feature details

## Feature Details

### 1. SCIM Integration
- **Category**: Identity Management
- **Complexity**: High
- **Target Segment**: Enterprise
- **Description**: Automated user provisioning and deprovisioning with identity provider integration

### 2. Periodic User Workflow
- **Category**: Automation
- **Complexity**: Medium
- **Target Segment**: All
- **Description**: Configurable recurring task execution with monitoring and error handling

### 3. Service-based Architecture
- **Category**: Architecture
- **Complexity**: High
- **Target Segment**: Enterprise
- **Description**: Microservices implementation with API-first design and fault tolerance

### 4. RDP for Unmanaged Devices
- **Category**: Remote Access
- **Complexity**: High
- **Target Segment**: All
- **Description**: Browser-based remote desktop with co-browsing for agentless environments

### 5. Minor/Major OS Patch Update
- **Category**: Patch Management
- **Complexity**: Medium
- **Target Segment**: All
- **Description**: Automated patch deployment with risk assessment and rollback capabilities

### 6. Discovery of Portable Applications
- **Category**: Asset Management
- **Complexity**: Medium
- **Target Segment**: Enterprise
- **Description**: Network-wide application discovery with compliance tracking and security analysis

## Prerequisites

1. Backend server must be running on the specified URL
2. Database must be initialized and accessible
3. Required Python packages: `httpx` (for async script) or `requests` (for sync module)

## Installation

```bash
# Install required packages
pip install httpx requests

# Or if using requirements.txt
pip install -r requirements.txt
```

## Expected Output

```
🚀 Starting feature initialization...
📊 Will create 6 features
------------------------------------------------------------
📝 Creating epic...
✅ Created epic: Core Platform Features Initiative (ID: 123e4567-e89b-12d3-a456-426614174000)

🔧 Creating features...
[1/6] Creating: SCIM Integration
✅ Created feature: SCIM Integration (ID: 123e4567-e89b-12d3-a456-426614174001)

[2/6] Creating: Periodic User Workflow
✅ Created feature: Periodic User Workflow (ID: 123e4567-e89b-12d3-a456-426614174002)

[3/6] Creating: Service-based Architecture
✅ Created feature: Service-based Architecture (ID: 123e4567-e89b-12d3-a456-426614174003)

[4/6] Creating: RDP for Unmanaged Devices (Co-browsing for Agentless Remote)
✅ Created feature: RDP for Unmanaged Devices (Co-browsing for Agentless Remote) (ID: 123e4567-e89b-12d3-a456-426614174004)

[5/6] Creating: Minor/Major OS Patch Update
✅ Created feature: Minor/Major OS Patch Update (ID: 123e4567-e89b-12d3-a456-426614174005)

[6/6] Creating: Discovery of Portable Applications
✅ Created feature: Discovery of Portable Applications (ID: 123e4567-e89b-12d3-a456-426614174006)

============================================================
🎉 Feature initialization completed successfully!
📈 Epic ID: 123e4567-e89b-12d3-a456-426614174000
📊 Features created: 6

📋 Created features:
  • SCIM Integration (ID: 123e4567-e89b-12d3-a456-426614174001)
  • Periodic User Workflow (ID: 123e4567-e89b-12d3-a456-426614174002)
  • Service-based Architecture (ID: 123e4567-e89b-12d3-a456-426614174003)
  • RDP for Unmanaged Devices (Co-browsing for Agentless Remote) (ID: 123e4567-e89b-12d3-a456-426614174004)
  • Minor/Major OS Patch Update (ID: 123e4567-e89b-12d3-a456-426614174005)
  • Discovery of Portable Applications (ID: 123e4567-e89b-12d3-a456-426614174006)

🔗 Next steps:
  1. Access the features through the web interface
  2. Run analysis on individual features as needed
  3. Add feature requests from customers
  4. Configure priority scoring

✨ Initialization complete: Successfully initialized 6 features
```

## Troubleshooting

### Common Issues

1. **Connection Error**: Ensure the backend server is running and accessible
2. **Authentication Error**: Check if API requires authentication tokens
3. **Database Error**: Verify database is initialized and migrations are applied
4. **Duplicate Features**: Features with same titles may already exist

### Error Handling

Both scripts include comprehensive error handling and will display detailed error messages if initialization fails.

## Next Steps

After initialization:

1. Access features through the web interface
2. Run feature analysis using the analysis endpoints
3. Add customer feature requests
4. Configure priority scoring
5. Generate reports and insights
