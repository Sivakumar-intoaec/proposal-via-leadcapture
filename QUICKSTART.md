# Quick Start Guide

## Installation & Setup

### 1. Install Dependencies

```bash
cd proposal-via-leadcapture
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### 2. Start the API Server

```bash
python app.py
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 3. Test the API

In another terminal, run the test script:

```bash
python app.py
```

This will run one end-to-end test and show the generated proposal summary.

---

## Quick API Test

### Using cURL

Generate a proposal:
```bash
curl -X POST http://localhost:8000/api/v1/generate-proposal \
  -H "Content-Type: application/json" \
  -d @example_lead_capture.json
```

### Using Python

```python
import requests
import json

# Load example data
with open("example_lead_capture.json") as f:
    data = json.load(f)

# Generate proposal
response = requests.post(
    "http://localhost:8000/api/v1/generate-proposal",
    json=data
)

# View result
result = response.json()
print(json.dumps(result, indent=2))

# Save to file
with open("proposal_output.json", "w") as f:
    json.dump(result, f, indent=2)
```

---

## Available Endpoint

```
POST /api/v1/generate-proposal
```

---

## Input Format

The API accepts either of these shapes:

1. Flat:
```json
{
  "leadCapture": { ... },
  "serviceTypes": { ... },
  "meta": { ... }
}
```

2. Wrapped:
```json
{
  "data": {
    "leadCapture": { ... },
    "serviceTypes": { ... }
  },
  "meta": { ... }
}
```

Your current frontend format can keep using the wrapped `data` object.

Example payload:

```json
{
  "data": {
    "leadCapture": {
    "fields": [
      {
        "fieldName": "fullName",
        "description": "Full Name",
        "type": "text",
        "required": true,
        "enabled": true
      }
    ]
    ]
    },
    "serviceTypes": {
    "fields": [
      {
        "serviceName": "Architecture",
        "tagline": "Service description",
        "isActive": true,
        "fields": [
          {
            "fieldName": "projectBudget",
            "description": "Budget",
            "type": "dropdown",
            "options": [
              {
                "label": "$500k-$1M",
                "price": 65000.0
              }
            ]
          }
        ]
      }
    ]
    ]
    }
  },
  "meta": {
    "currency": "USD",
    "country": "US"
  }
}
```

See `example_lead_capture.json` for a complete example.

---

## Output Format

The API returns:

```json
{
  "success": true,
  "message": "Proposal generated successfully",
  "proposal": {
    "title": "Project Title",
    "pages": [
      {
        "name": "Cover",
        "controllers": [...]
      },
      {
        "name": "Investment Breakdown",
        "controllers": [...]
      },
      {
        "name": "Pricing Justification",
        "controllers": [...]
      },
      {
        "name": "Acceptance & Next Steps",
        "controllers": [...]
      }
    ],
    "pricingTable": {
      "header": [...],
      "content": [...],
      "summary": {
        "subtotal": 100000.0,
        "contingency": 10000.0,
        "total": 110000.0
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
      "subtotal": 100000.0,
      "contingency": 10000.0,
      "total": 110000.0
    },
    "justifications": {...}
  },
  "justificationText": [...],
  "timestamp": "2026-05-25T10:30:00"
}
```

---

## Troubleshooting

### API won't start
- Make sure Python 3.11+ is installed
- If you're on Python 3.13, recreate the virtual environment after updating dependencies
- Verify all dependencies: `pip install -r requirements.txt`
- Try a different port: `API_PORT=8001 python app.py`

### Pydantic build error on Windows
- If you see a `pydantic-core` build failure on Python 3.13, you are likely using an old cached environment or stale dependency pin
- Upgrade pip first, then reinstall from the updated `requirements.txt`
- If the error persists, delete and recreate `.venv` so pip resolves the newer Pydantic wheel cleanly

### Import errors
- Ensure you're in the correct directory
- Check that `app.py` is in the project root

### Request fails
- Check that the JSON format matches the example
- Ensure all required fields are present
- Look at the error message in the API response

### Port already in use
- List processes: `lsof -i :8000` (macOS/Linux)
- Kill process: `kill -9 <PID>`
- Or use a different port: `API_PORT=8001 python app.py`

---

## Next Steps

1. ✅ API is running and tested
2. 📝 Use `example_lead_capture.json` as a template
3. 🔗 Integrate API endpoints into your frontend
4. 📊 Process proposal JSON through proposal generator
5. 📄 Convert to PDF using your preferred tool

---

## Documentation

- Full API docs: http://localhost:8000/docs
- README with detailed endpoints: See `README.md`
- Example input: `example_lead_capture.json`

---

## Support

Check the full README.md for:
- Detailed endpoint documentation
- Architecture overview
- Integration examples
- Performance metrics
- Future enhancements

```bash
# View documentation
cat README.md
```
