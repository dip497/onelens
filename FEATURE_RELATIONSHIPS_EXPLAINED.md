# Feature Relationships in OneLens

## 🎯 Understanding the Dual Nature of Features

### The Two Systems

1. **Epic Management System** (Original)
   - Path: Epic → Features
   - Purpose: Product development and roadmap planning
   - Required: Every feature MUST belong to an Epic
   - Used for: Planning sprints, tracking development progress

2. **Persona/Product System** (New)
   - Path: Product → Modules → Features
   - Purpose: Sales enablement and competitive positioning
   - Optional: Features CAN be assigned to Product Modules
   - Used for: Battle cards, competitor comparisons, sales materials

## 📊 Data Model

```sql
CREATE TABLE features (
    id UUID PRIMARY KEY,
    epic_id UUID NOT NULL REFERENCES epics(id),      -- REQUIRED: Development tracking
    module_id UUID REFERENCES product_modules(id),    -- OPTIONAL: Product positioning
    title VARCHAR(255) NOT NULL,
    description TEXT,
    is_key_differentiator BOOLEAN DEFAULT FALSE,      -- For battle cards
    ...
);
```

## 🔄 How It Works

### Workflow Example:

1. **Product Team creates an Epic**: "AI-Powered Analytics"
2. **Features are added to the Epic**:
   - "Real-time dashboard"
   - "Predictive analytics"
   - "Custom report builder"

3. **Product Marketing assigns features to Modules**:
   - "Real-time dashboard" → "Core Features" module
   - "Predictive analytics" → "AI & Intelligence" module
   - "Custom report builder" → "Analytics" module

4. **Sales team uses this for Battle Cards**:
   - Shows which features are in which product modules
   - Highlights key differentiators
   - Compares with competitor features

## 🎨 Visual Representation

```
DEVELOPMENT VIEW:
Epic: "AI Analytics"
├── Feature: "Real-time dashboard"
├── Feature: "Predictive analytics"
└── Feature: "Custom report builder"

SALES/MARKETING VIEW:
Product: "OneLens"
├── Module: "Core Features"
│   └── Feature: "Real-time dashboard" (from AI Analytics epic)
├── Module: "AI & Intelligence"
│   └── Feature: "Predictive analytics" (from AI Analytics epic)
└── Module: "Analytics"
    └── Feature: "Custom report builder" (from AI Analytics epic)
```

## 💡 Key Points

1. **Features are shared** between Epic management and Product modules
2. **Epic assignment is mandatory** - every feature needs development context
3. **Module assignment is optional** - only customer-facing features need marketing context
4. **is_key_differentiator flag** - marks features that set you apart from competitors

## 🛠️ Frontend Implementation

### Epic Dashboard
- Shows features grouped by Epic
- Used by: Product Managers, Developers
- Focus: Development status, timelines

### Persona/Product Dashboard  
- Shows features grouped by Module
- Used by: Sales, Marketing
- Focus: Customer value, competitive positioning

## 📝 API Endpoints

### For Epic Management:
- `GET /api/v1/epics/{epic_id}/features` - Features for development
- `POST /api/v1/features` - Create feature (requires epic_id)

### For Product/Persona:
- `GET /api/v1/products/{product_id}/modules/{module_id}/features` - Features for sales
- `POST /api/v1/features/batch-update` - Assign features to modules
- `PUT /api/v1/modules/{module_id}/features` - Update module assignments

## ✅ Benefits of This Approach

1. **No duplication** - Single source of truth for features
2. **Flexible assignment** - Features can be reorganized for different audiences
3. **Clear separation** - Development vs. Sales/Marketing views
4. **Maintains relationships** - Can trace feature from idea to customer value

## 🚨 Important Notes

- When creating a feature, you MUST specify an epic_id
- Module assignment can be done later through the Persona dashboard
- A feature can belong to only ONE epic but can be shown in ONE module
- Deleting an epic will delete all its features (CASCADE)
- Removing a module will just unassign features (SET NULL)

This dual-purpose design allows OneLens to bridge the gap between product development and go-to-market strategy!