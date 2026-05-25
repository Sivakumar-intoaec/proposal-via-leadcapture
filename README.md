# Lead Capture to Proposal API

Convert lead capture form data to professional proposals with dynamic pricing tables and detailed pricing justifications.

## Features

✅ **Pricing Engine**
- Extracts pricing from service types and field options
- Calculates subtotals, contingency, and grand totals
- Supports price matrix and multi-select pricing

✅ **Proposal Builder**
- Generates multi-page proposals
- Cover page with project details
- Pricing breakdown page with interactive table
- Justification page explaining pricing rationale
- Acceptance/signature page

✅ **REST API**
- FastAPI-based endpoints
- CORS-enabled for cross-origin requests
- Multiple endpoints for different use cases
- Pydantic models for request/response validation

✅ **Intelligent Pricing Justifications**
- Timeline complexity analysis
- Location-based adjustments
- Service complexity multipliers
- Contingency allocation explanation

## Installation

### Prerequisites
- Python 3.11+
- pip or conda

### Setup

```bash
# Navigate to the project directory
cd proposal-via-leadcapture

# Keep build tooling current, especially on Python 3.13
python -m pip install --upgrade pip setuptools wheel

# Install dependencies
pip install -r requirements.txt
```

If you are using Python 3.13, make sure you are on the updated dependency set in this repository. Older cached virtual environments can still try to build an incompatible `pydantic-core` release from source.

## Running the API

### Development Mode

```bash
python api.py
```

Or with uvicorn directly:

```bash
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

### Production Mode

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --workers 4
```

The API will be available at: `http://localhost:8000`

### API Documentation

- **Interactive Docs (Swagger UI)**: http://localhost:8000/docs
- **Alternative Docs (ReDoc)**: http://localhost:8000/redoc

## API Endpoints

### Generate Proposal
```
POST /api/v1/generate-proposal
```

Generates a complete proposal with all pages, a pricing table, and justification text.

**Request Body:**
```json
{
  "leadCapture": {
    "fields": [
      {
        "fieldName": "fullName",
        "description": "Full Name",
        "type": "text",
        "required": true,
        "enabled": true,
        "orderIndex": 0
      },
      {
        "fieldName": "email",
        "description": "Email Address",
        "type": "email",
        "required": true,
        "enabled": true,
        "orderIndex": 1
      }
    ]
  },
  "serviceTypes": {
    "fields": [
      {
        "serviceName": "Architecture",
        "tagline": "Bespoke luxury villa design",
        "icon": "home",
        "configured": true,
        "isActive": true,
        "fields": [
          {
            "fieldName": "projectBudget",
            "description": "Total Project Budget Range",
            "type": "dropdown",
            "options": [
              {
                "label": "$500,000 - $1,000,000",
                "price": 65000.0
              }
            ],
            "priceMatrixEnabled": true,
            "required": true,
            "enabled": true,
            "orderIndex": 0
          }
        ]
      }
    ]
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Proposal generated successfully",
  "proposal": {
    "title": "Architecture Project Proposal",
    "subtitle": "Professional Design & Development Services",
    "pages": [
      {
        "name": "Cover",
        "type": "cover",
        "layout": "hero_bold_type",
        "controllers": [...]
      },
      {
        "name": "Investment Breakdown",
        "type": "investment",
        "controllers": [...]
      },
      {
        "name": "Pricing Justification",
        "type": "content",
        "controllers": [...]
      },
      {
        "name": "Acceptance & Next Steps",
        "type": "acceptance",
        "controllers": [...]
      }
    ],
    "pricingTable": {
      "header": [...],
      "content": [...],
      "summary": {
        "subtotal": 65000.0,
        "contingency": 6500.0,
        "total": 71500.0,
        "currency": "USD"
      },
      "justifications": {...}
    },
    "justificationText": [
      {
        "key": "service_selection",
        "text": "..."
      }
    ]
  },
  "pricingTable": {
    "header": [...],
    "content": [...],
    "summary": {
      "subtotal": 65000.0,
      "contingency": 6500.0,
      "total": 71500.0,
      "currency": "USD"
    },
    "justifications": {...}
  },
  "justificationText": [...],
  "timestamp": "2026-05-25T10:30:00"
}
```

---

## Usage Examples

### Using cURL

```bash
curl -X POST http://localhost:8000/api/v1/generate-proposal \
  -H "Content-Type: application/json" \
  -d @lead_capture_input.json
```

### Using Python Requests

```python
import requests
import json

# Load the lead capture JSON
with open("lead_capture_input.json") as f:
    data = json.load(f)

response = requests.post(
    "http://localhost:8000/api/v1/generate-proposal",
    json=data
)

proposal = response.json()
print(json.dumps(proposal, indent=2))

# Export as file
with open("proposal_output.json", "w") as f:
    json.dump(proposal, f, indent=2)
```

### Using JavaScript/Node.js

```javascript
const axios = require('axios');
const fs = require('fs');

// Load lead capture data
const leadData = JSON.parse(fs.readFileSync('lead_capture_input.json', 'utf8'));

// Generate proposal
axios.post('http://localhost:8000/api/v1/generate-proposal', leadData)
  .then(response => {
    console.log(JSON.stringify(response.data, null, 2));
    
    // Save proposal
    fs.writeFileSync('proposal_output.json', JSON.stringify(response.data, null, 2));
  })
  .catch(error => console.error('Error:', error));
```

---

## Data Structure

### Lead Capture Form Field

```python
{
  "fieldName": "string",           # Unique field identifier
  "description": "string",         # Display name/label
  "type": "text|email|phone|dropdown|multiselect|textarea",
  "options": [                     # For dropdown/multiselect
    {
      "label": "string",           # Option display text
      "price": float              # Associated price
    }
  ],
  "required": bool,                # Is field mandatory
  "enabled": bool,                 # Is field active
  "orderIndex": int                # Display order
}
```

### Service Type

```python
{
  "serviceName": "string",        # e.g., "Architecture", "Interior Design"
  "tagline": "string",            # Service description
  "icon": "string",               # Icon identifier
  "configured": bool,             # Is service configured
  "isActive": bool,               # Is service available for selection
  "fields": [...]                 # Array of FormField objects
}
```

---

## Pricing Logic

### Pricing Calculation

1. **Service Selection**: Each service type includes multiple fields with price-associated options
2. **Base Price**: Sum of selected options' prices
3. **Complexity Multiplier**: Applied based on:
   - Project timeline (1-3 months: 1.15x, 3-6 months: 1.05x)
   - Location (International: 1.10x)
4. **Contingency**: 10% of subtotal (standard industry practice)
5. **Grand Total**: Subtotal + Contingency

### Pricing Justification Factors

- **Service Selection**: Professional expertise and quality assurance
- **Timeline Premium**: Rush projects (1-3 months) incur 15% premium
- **Location Impact**: International projects add 10% for travel/logistics
- **Contingency Reserve**: 10% for unforeseen changes or scope clarifications

---

## Integration with Proposal Generator

The output from this API is designed to work with the main proposal generator (`generator.py`). The JSON output includes:

- **Proposal Structure**: Multi-page layout with controllers
- **Pricing Tables**: PRICING_TABLE controller compatible
- **Macros**: Uses standard IntoAEC macros ({LEAD_NAME}, {LEAD_EMAIL}, etc.)
- **Text Controllers**: Properly formatted TEXT blocks
- **Shape Controllers**: Background and accent elements

To convert the proposal JSON to a PDF, pipe it to the proposal generator:

```bash
python api_server.py --input proposal_output.json --output proposal.pdf
```

---

## Architecture

```
proposal-via-leadcapture/
├── api.py                 # FastAPI main server
├── pricing_engine.py      # Pricing calculation logic
├── proposal_builder.py    # Proposal page generation
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

### Components

1. **PricingEngine** (`pricing_engine.py`)
   - `parse_lead_capture()`: Extract form field metadata
   - `build_pricing_from_services()`: Calculate prices from service data
   - `analyze_service_complexity()`: Determine pricing multipliers
   - `generate_justifications()`: Create pricing explanations
   - `build_proposal_pricing_table()`: Generate final pricing table

2. **ProposalBuilder** (`proposal_builder.py`)
   - `build_cover_page()`: Generate title/cover page
   - `build_pricing_page()`: Create pricing breakdown page
   - `build_justification_page()`: Add pricing explanation page
   - `build_acceptance_page()`: Generate signature page
   - `build_complete_proposal()`: Assemble all pages

3. **FastAPI Server** (`api.py`)
   - Single AI-powered endpoint for proposal generation
   - Pydantic models for validation
   - CORS middleware for cross-origin requests
   - Error handling and logging

---

## Configuration

### Environment Variables

Create a `.env` file in the project directory:

```
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4
DEBUG=False
DIGITALOCEAN_API_KEY=your_digitalocean_inference_key_here
DIGITALOCEAN_URL=https://inference.do-ai.run
DIGITALOCEAN_MODEL=anthropic-claude-4.5-sonnet
```

Load with:
```python
from dotenv import load_dotenv
import os

load_dotenv()
api_host = os.getenv("API_HOST", "0.0.0.0")
currency = os.getenv("DEFAULT_CURRENCY", "USD")
```

---

## Error Handling

### Common Errors

**400 - Bad Request**
```json
{
  "success": false,
  "message": "Error",
  "error": "Invalid lead capture JSON structure"
}
```

**500 - Internal Server Error**
```json
{
  "success": false,
  "message": "Error",
  "error": "Internal server error: [details]"
}
```

---

## Performance

- **Pricing Calculation**: ~50-100ms
- **Proposal Generation**: ~200-300ms
- **Full API Response**: ~300-500ms

---

## Future Enhancements

- [x] Support for multiple currencies in request metadata
- [ ] Dynamic pricing adjustments based on project scope
- [ ] PDF export directly from API
- [ ] Email delivery of proposals
- [ ] Proposal versioning and history
- [ ] Custom branding support
- [ ] Multi-language support
- [ ] Discount and promotional code support

---

## Support

For issues or questions:
1. Check the API docs: http://localhost:8000/docs
2. Review the example input: `example_lead_capture.json`
3. Check error messages in API response

---

## License

Proprietary - IntoAEC Project Proposal System
#   p r o p o s a l - v i a - l e a d c a p t u r e  
 