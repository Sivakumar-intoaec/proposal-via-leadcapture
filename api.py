"""
Lead Capture to Proposal API v1
================================
Single FastAPI endpoint that converts lead capture form data into one
combined JSON payload containing the proposal pages, pricing table, and
pricing justification text blocks.

Usage:
  POST /api/v1/generate-proposal
  Content-Type: application/json
  Body: Lead capture form JSON
"""

from datetime import datetime
import json
import os
import sys
import re
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pricing_engine import PricingEngine
from proposal_builder import ProposalBuilder

# Initialize FastAPI app
app = FastAPI(
    title="Lead Capture to Proposal API",
    description="Convert lead capture forms into one proposal JSON payload with pricing tables and justifications",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class FieldOption(BaseModel):
    label: str
    price: float


class FormField(BaseModel):
    fieldName: str
    description: str
    type: str
    options: Optional[List[FieldOption]] = None
    required: bool = False
    enabled: bool = True
    orderIndex: int = 0


class LeadCaptureData(BaseModel):
    fields: List[FormField]


class ServiceField(BaseModel):
    fieldName: str
    description: str
    type: str
    options: Optional[List[FieldOption]] = None
    priceMatrixEnabled: bool = False
    required: bool = False
    enabled: bool = True
    orderIndex: int = 0


class ServiceType(BaseModel):
    serviceName: str
    tagline: str
    icon: str
    configured: bool = True
    isActive: bool = True
    fields: List[ServiceField] = Field(default_factory=list)


class ServiceTypesData(BaseModel):
    fields: List[ServiceType]


class MetaData(BaseModel):
    model: str = "anthropic-claude-4.5-sonnet"
    currency: str = "USD"
    country: str = "US"
    city: Optional[str] = None


class LeadCaptureRequest(BaseModel):
    leadCapture: LeadCaptureData
    serviceTypes: ServiceTypesData
    meta: Optional[MetaData] = None


class ProposalResponse(BaseModel):
    success: bool
    message: str
    proposal: Dict[str, Any] = Field(default_factory=dict)
    pricingTable: Optional[Dict[str, Any]] = None
    justificationText: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: str


def extract_json_payload(text: str) -> Dict[str, Any]:
    """Extract JSON from a model response that may include fences or prose."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]

    return json.loads(cleaned)


def normalize_request_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Accept both:
    - {"leadCapture": ..., "serviceTypes": ..., "meta": ...}
    - {"data": {"leadCapture": ..., "serviceTypes": ...}, "meta": ...}
    """
    if "data" in payload and isinstance(payload["data"], dict):
        inner = payload["data"]
        normalized = {
            "leadCapture": inner.get("leadCapture"),
            "serviceTypes": inner.get("serviceTypes"),
            "meta": payload.get("meta", inner.get("meta"))
        }
    else:
        normalized = {
            "leadCapture": payload.get("leadCapture"),
            "serviceTypes": payload.get("serviceTypes"),
            "meta": payload.get("meta")
        }

    return normalized


def call_digitalocean_ai(form_data: Dict[str, Any], pricing_table: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    """Generate proposal copy with DigitalOcean inference."""
    api_key = os.getenv("DIGITALOCEAN_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="DIGITALOCEAN_API_KEY is not configured. Add it to your .env file."
        )

    base_url = os.getenv("DIGITALOCEAN_URL", "https://inference.do-ai.run").rstrip("/")
    model_name = (
        (form_data.get("meta") or {}).get("model")
        or os.getenv("DIGITALOCEAN_MODEL", "anthropic-claude-4.5-sonnet")
    )

    lead_fields = [field.get("description") for field in form_data.get("leadCapture", {}).get("fields", []) if field.get("description")]
    service_names = [service.get("serviceName") for service in form_data.get("serviceTypes", {}).get("fields", []) if service.get("isActive")]
    location = (form_data.get("meta", {}) or {}).get("city") or form_data.get("projectLocation", "") or "Client location"
    timeline = form_data.get("projectTimeline", "") or "Not specified"

    prompt_payload = {
        "currency": currency_code,
        "leadFields": lead_fields,
        "serviceNames": service_names,
        "projectLocation": location,
        "projectTimeline": timeline,
        "pricingSummary": pricing_table.get("summary", {}),
        "pricingJustifications": pricing_table.get("justifications", {}),
    }

    prompt = f"""
You are writing premium proposal copy for an architecture and interior design proposal system.

Use the provided currency code everywhere pricing is mentioned: {currency_code}
Return ONLY valid JSON. Do not wrap it in markdown or commentary.

Create this JSON object:
{{
  "title": "A concise project title",
  "subtitle": "A short premium subtitle",
  "pricing_intro": "One paragraph introducing the pricing table",
  "justification_title": "A strong section title for pricing justification",
  "justification_sections": [
    "Paragraph 1 explaining service selection and scope.",
    "Paragraph 2 explaining timeline or location impact.",
    "Paragraph 3 explaining contingency or value."
  ],
  "acceptance_intro": "A short paragraph for the signature/acceptance page"
}}

Context JSON:
{json.dumps(prompt_payload, ensure_ascii=True)}
""".strip()

    endpoint = (
        f"{base_url}/chat/completions"
        if base_url.endswith("/v1")
        else f"{base_url}/v1/chat/completions"
    )

    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a proposal-writing assistant that returns strict JSON only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.2,
            "max_completion_tokens": 1200
        },
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return extract_json_payload(content)


@app.post("/api/v1/generate-proposal", response_model=ProposalResponse)
async def generate_proposal(request: Dict[str, Any]):
    """
    Generate one combined proposal JSON payload.

    This endpoint accepts the lead capture form payload and returns:
    - proposal pages
    - pricing table
    - justification text blocks
    """
    try:
        normalized_payload = normalize_request_payload(request)
        validated_request = LeadCaptureRequest.model_validate(normalized_payload)
        currency_code = (validated_request.meta.currency if validated_request.meta else "USD").upper()

        form_data = {
            "leadCapture": validated_request.leadCapture.model_dump(),
            "serviceTypes": validated_request.serviceTypes.model_dump(),
            "meta": validated_request.meta.model_dump() if validated_request.meta else {}
        }

        pricing_engine = PricingEngine()
        pricing_table = pricing_engine.build_proposal_pricing_table(form_data, currency_code)
        justifications = pricing_table.get("justifications", {})

        ai_content = call_digitalocean_ai(form_data, pricing_table, currency_code)

        builder = ProposalBuilder(form_data, ai_content=ai_content)
        proposal = builder.build_complete_proposal()

        ai_justification_sections = ai_content.get("justification_sections", [])
        if isinstance(ai_justification_sections, list) and ai_justification_sections:
            justification_text = [
                {"key": f"section_{index + 1}", "text": section}
                for index, section in enumerate(ai_justification_sections)
                if isinstance(section, str) and section.strip()
            ]
        else:
            justification_text = [
                {
                    "key": key,
                    "text": value
                }
                for key, value in justifications.items()
            ]

        proposal["pricingTable"] = pricing_table
        proposal["justificationText"] = justification_text

        return ProposalResponse(
            success=True,
            message="Proposal generated successfully",
            proposal=proposal,
            pricingTable=pricing_table,
            justificationText=justification_text,
            timestamp=datetime.now().isoformat()
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
