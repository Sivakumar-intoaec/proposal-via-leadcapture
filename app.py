"""
Single-file Lead Capture to Proposal API
========================================
One endpoint:
  POST /api/v1/generate-proposal

Returns:
  - pages
  - macros

The proposal content is generated with DigitalOcean AI when available.
Pricing and page structure are built in this file only.
"""

from __future__ import annotations

import json
import os
import re
import traceback
from datetime import datetime
from uuid import uuid4
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(
    title="Lead Capture to Proposal API",
    description="Single endpoint proposal generator",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def uid() -> str:
    return str(uuid4())


def now_ms() -> str:
    return str(int(datetime.now().timestamp() * 1000))


def normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(payload.get("data"), dict):
        payload = {**payload["data"], "meta": payload.get("meta", payload["data"].get("meta"))}
    return {
        "leadCapture": payload.get("leadCapture") or {},
        "serviceTypes": payload.get("serviceTypes") or {},
        "meta": payload.get("meta") or {},
    }


def currency_symbol(code: str) -> str:
    return {
        "USD": "$",
        "INR": "₹",
        "EUR": "€",
        "GBP": "£",
        "AED": "AED ",
        "SAR": "SAR ",
        "QAR": "QAR ",
        "CAD": "C$",
        "AUD": "A$",
    }.get((code or "USD").upper(), f"{(code or 'USD').upper()} ")


def money(amount: float, code: str) -> str:
    return f"{currency_symbol(code)}{amount:,.2f}"


def text_block(text: str, font_size: int = 13, color: str = "#333333", bold: bool = False, italic: bool = False) -> Dict[str, Any]:
    child: Dict[str, Any] = {"text": text, "fontSize": font_size, "color": color}
    if bold:
        child["bold"] = True
    if italic:
        child["italic"] = True
    return {
        "type": "p",
        "children": [child],
        "lineHeight": 1.8,
    }


def heading_block(text: str, level: str = "h2", font_size: int = 18, color: str = "#1a1a2e") -> Dict[str, Any]:
    return {
        "type": level,
        "children": [{"text": text, "fontSize": font_size, "color": color, "bold": True}],
        "lineHeight": 1.4,
    }


def make_text_controller(x: int, y: int, width: Any, blocks: List[Dict[str, Any]], height: Any = "auto") -> Dict[str, Any]:
    return {
        "controllerId": uid(),
        "controllerName": "TEXT",
        "style": {"width": width, "height": height} if height == "auto" else {"width": width, "height": height},
        "x": x,
        "y": y,
        "value": blocks,
    }


def make_shape_controller(x: int, y: int, width: int, height: int, background: str, border_radius: int = 0) -> Dict[str, Any]:
    return {
        "controllerId": uid(),
        "controllerName": "SHAPE",
        "style": {
            "width": width,
            "height": height,
            "backgroundColor": background,
            "borderRadius": border_radius,
        },
        "x": x,
        "y": y,
        "value": {"shape": "rectangle", "isLocked": False},
    }


def make_image_controller(x: int, y: int, width: int, height: int, url: str) -> Dict[str, Any]:
    return {
        "controllerId": uid(),
        "controllerName": "IMAGE",
        "style": {"width": width, "height": height, "borderRadius": 0},
        "x": x,
        "y": y,
        "value": {"fileName": "file", "fileType": "image/jpeg", "url": url, "description": ""},
    }


def make_divider(x: int, y: int, width: int = 695) -> Dict[str, Any]:
    return {
        "controllerId": uid(),
        "controllerName": "DIVIDER",
        "style": {"width": f"{width}px", "height": "1px"},
        "x": x,
        "y": y,
    }


def lead_value(form_data: Dict[str, Any], field_name: str, default: str = "") -> str:
    meta = form_data.get("meta", {}) or {}
    if field_name == "projectLocation":
        return str(meta.get("city") or default)
    if field_name == "fullName":
        return "{LEAD_NAME}"
    if field_name == "email":
        return "{LEAD_EMAIL}"
    if field_name == "phone":
        return "{LEAD_PHONE_NUMBER}"
    return default


def build_macros(form_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    field_names = {
        field.get("fieldName", "")
        for field in form_data.get("leadCapture", {}).get("fields", [])
        if field.get("fieldName")
    }
    macros: List[Dict[str, Any]] = []

    def add(label: str, param: str, category: str, macro_type: str = "string") -> None:
        macros.append(
            {
                "macrosId": uid(),
                "macroSource": "COMMON" if category == "COMMON" else "LEADMANAGER",
                "macroCategory": category,
                "macroSubCategory": None,
                "endpoint": None,
                "macroTableName": None,
                "macroColumnName": None,
                "entityColumnName": None,
                "staticMacro": category == "COMMON",
                "selectable": False,
                "isIntoAEC": False,
                "macroColumnType": macro_type,
                "macroLabel": label,
                "macroParam": param,
                "createdBy": "AI_GENERATOR",
                "createdAt": now_ms(),
                "updatedBy": None,
                "updatedAt": now_ms(),
            }
        )

    if "fullName" in field_names:
        add("LEAD_NAME", "{LEAD_NAME}", "LEADS")
    if "email" in field_names:
        add("LEAD_EMAIL", "{LEAD_EMAIL}", "LEADS")
    if "phone" in field_names:
        add("LEAD_PHONE_NUMBER", "{LEAD_PHONE_NUMBER}", "LEADS")
    if "projectLocation" in field_names:
        add("LEAD_PROJECT_LOCATION", "{LEAD_PROJECT_LOCATION}", "LEADS")

    add("ORGANIZATION_NAME", "{ORGANIZATION_NAME}", "ORGANIZATION")
    add("CURRENT_DATE", "{CURRENT_DATE}", "COMMON", "date")
    return macros


def parse_services(form_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    services = form_data.get("serviceTypes", {}).get("fields", []) or []
    return [s for s in services if s.get("isActive", True)]


def extract_items(form_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for service in parse_services(form_data):
        service_name = service.get("serviceName", "Service")
        for field in service.get("fields", []) or []:
            options = field.get("options") or []
            if not options:
                continue

            field_type = field.get("type", "")
            label = field.get("description", field.get("fieldName", "Item"))
            if field_type == "multiselect":
                price = sum(float(opt.get("price", 0)) for opt in options)
                item_label = f"{label} (Multi-service)"
            else:
                price = sum(float(opt.get("price", 0)) for opt in options) / len(options)
                item_label = label

            items.append(
                {
                    "itemName": item_label,
                    "category": service_name,
                    "basePrice": float(price),
                    "quantity": 1,
                    "justification": f"Pricing based on {field.get('fieldName', 'selected field')}",
                }
            )
    return items


def build_pricing_table(form_data: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    items = extract_items(form_data)
    subtotal = sum(item["basePrice"] * item["quantity"] for item in items)
    contingency = subtotal * 0.10
    total = subtotal + contingency

    content: List[List[Dict[str, Any]]] = []
    seen = set()
    for item in items:
        if item["category"] not in seen:
            seen.add(item["category"])
            content.append(
                [
                    {"value": f"{item['category']} Services", "label": item["category"], "isHeader": True},
                    {"value": "", "label": "", "isHeader": True},
                    {"value": "", "label": "", "isHeader": True},
                ]
            )
        content.append(
            [
                {"value": item["itemName"]},
                {"value": money(item["basePrice"], currency_code)},
                {"value": str(item["quantity"])},
            ]
        )

    content.extend(
        [
            [{"value": "Subtotal", "bold": True}, {"value": money(subtotal, currency_code), "bold": True}, {"value": ""}],
            [{"value": "Contingency (10%)"}, {"value": money(contingency, currency_code)}, {"value": ""}],
            [{"value": "Total Project Cost", "bold": True}, {"value": money(total, currency_code), "bold": True}, {"value": ""}],
        ]
    )

    justifications = {
        "service_selection": "Pricing is based on selected service categories and complexity levels. Each service tier includes professional expertise, project management, and quality assurance.",
        "timeline_premium": "Standard Timeline: 6+ month timeline allows efficient phasing and resource optimization.",
        "location_impact": f"Location-based Adjustments: Project location ({(form_data.get('meta') or {}).get('city', '')}) impacts travel, logistics, and local compliance requirements.",
        "contingency": "10% Contingency Reserve: Industry-standard allocation for unforeseen project changes, site conditions, or scope clarifications.",
    }

    return {
        "header": [
            {"value": "Service / Item", "label": "Service"},
            {"value": "Price", "label": "Price"},
            {"value": "Qty", "label": "Quantity"},
        ],
        "content": content,
        "summary": {
            "subtotal": subtotal,
            "contingency": contingency,
            "total": total,
            "currency": currency_code,
        },
        "justifications": justifications,
    }


def fallback_ai_content(form_data: Dict[str, Any], pricing_table: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    city = (form_data.get("meta") or {}).get("city") or "your project location"
    total = money(pricing_table["summary"]["total"], currency_code)
    contingency = money(pricing_table["summary"]["contingency"], currency_code)
    return {
        "title": "Architecture & Design Services Proposal",
        "subtitle": f"Comprehensive architectural solutions tailored for {city}",
        "pricing_intro": f"The following investment structure reflects the comprehensive scope of architectural services required for your project in {city}.",
        "justification_title": "Investment Breakdown & Value Framework",
        "justification_sections": [
            f"Your investment of {money(pricing_table['summary']['subtotal'], currency_code)} is structured around the selected services and project complexity.",
            f"The pricing structure incorporates location-specific considerations for your {city} project and allows flexibility in phasing and resource allocation.",
            f"A 10% contingency reserve of {contingency} has been included as an industry-standard safeguard, bringing your total investment to {total}.",
        ],
        "acceptance_intro": "We're honored by the opportunity to bring your architectural vision to life. By signing below, you authorize us to commence work under the terms outlined in this proposal.",
    }


def clean_json_text(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def call_digitalocean_ai(form_data: Dict[str, Any], pricing_table: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    api_key = (
        os.getenv("DIGITALOCEAN_API_KEY")
        or os.getenv("DIGITALOCEAN_TOKEN")
        or os.getenv("MODEL_ACCESS_KEY")
        or ""
    ).strip()
    if not api_key:
        return fallback_ai_content(form_data, pricing_table, currency_code)

    base_url = os.getenv("DIGITALOCEAN_URL", "https://inference.do-ai.run").rstrip("/")
    model_name = (form_data.get("meta") or {}).get("model") or os.getenv("DIGITALOCEAN_MODEL", "anthropic-claude-4.5-sonnet")
    endpoint = f"{base_url}/chat/completions" if base_url.endswith("/v1") else f"{base_url}/v1/chat/completions"

    prompt_payload = {
        "currency": currency_code,
        "city": (form_data.get("meta") or {}).get("city", ""),
        "services": [s.get("serviceName") for s in parse_services(form_data)],
        "pricingSummary": pricing_table["summary"],
        "pricingJustifications": pricing_table["justifications"],
    }

    prompt = f"""
Return ONLY valid JSON with these keys:
title, subtitle, pricing_intro, justification_title, justification_sections, acceptance_intro

Context:
{json.dumps(prompt_payload, ensure_ascii=True)}
""".strip()

    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "You are a proposal-writing assistant that returns strict JSON only."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_completion_tokens": 1200,
            },
            timeout=90,
        )
        if not response.ok:
            return fallback_ai_content(form_data, pricing_table, currency_code)
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        result = clean_json_text(content)
        if not isinstance(result, dict):
            return fallback_ai_content(form_data, pricing_table, currency_code)
        return result
    except Exception:
        return fallback_ai_content(form_data, pricing_table, currency_code)


def page_base(page_name: str) -> Dict[str, Any]:
    return {"pageId": uid(), "pageName": page_name, "controllers": []}


def build_cover_page(form_data: Dict[str, Any], ai: Dict[str, Any]) -> Dict[str, Any]:
    meta = form_data.get("meta") or {}
    title = ai.get("title") or "Proposal"
    subtitle = ai.get("subtitle") or "Professional Services"
    city = meta.get("city") or "Project Location"
    date_text = datetime.now().strftime("%d %B %Y")
    page = page_base("Cover")
    page["controllers"] = [
        make_shape_controller(0, 0, 791, 860, "rgba(13,17,38,1)"),
        make_shape_controller(0, 0, 791, 420, "rgba(13,17,38,0.55)"),
        make_shape_controller(0, 0, 791, 5, "rgba(192,154,77,1)"),
        {
            "controllerId": uid(),
            "controllerName": "ORGANIZATION_LOGO",
            "style": {"width": "140px", "height": "50px"},
            "x": 48,
            "y": 20,
            "value": "",
        },
        make_text_controller(48, 24, "480px", [text_block("DOC REF: PROPOSAL_" + now_ms(), 10, "#c09a4d")]),
        make_text_controller(66, 120, "560px", [heading_block(title, "h1", 42, "#ffffff")]),
        make_text_controller(66, 182, "560px", [heading_block(subtitle, "h2", 22, "#c09a4d")]),
        make_text_controller(66, 225, "560px", [text_block("PROPOSAL  ·  DRAFT", 14, "#cbd5e0")]),
        make_shape_controller(0, 340, 791, 80, "rgba(13,17,38,0.85)"),
        make_text_controller(66, 355, "180px", [text_block("PREPARED BY", 9, "#c09a4d", True), text_block((meta.get("organizationName") or "Our Studio"), 13, "#ffffff", True), text_block("Architecture & Design", 11, "#9ca3af")]),
        make_text_controller(310, 355, "180px", [text_block("CLIENT", 9, "#c09a4d", True), text_block("{LEAD_NAME}", 13, "#ffffff", True)]),
        make_text_controller(554, 355, "200px", [text_block("DATE", 9, "#c09a4d", True), text_block(date_text, 13, "#ffffff", True), text_block(city, 11, "#9ca3af")]),
        make_shape_controller(0, 420, 791, 4, "rgba(192,154,77,1)"),
        make_text_controller(66, 442, "480px", [heading_block("01  EXECUTIVE SUMMARY", "h2", 18, "#1a1a2e")]),
        make_shape_controller(48, 440, 5, 38, "rgba(192,154,77,1)", 3),
        make_text_controller(48, 494, "695px", [text_block("This proposal presents a tailored concept for your project, integrating the selected services, pricing, and project approach.", 13, "#1a1a2e", False, True)]),
        make_text_controller(48, 558, "695px", [text_block("The proposal is structured to help you review the scope, understand the investment, and confirm the next steps.", 13, "#3a3a5c"), text_block("It combines clear pricing with a presentation format suitable for client review and approval.", 13, "#3a3a5c")]),
        make_shape_controller(0, 856, 791, 4, "rgba(192,154,77,1)"),
    ]
    return page


def build_pricing_page(form_data: Dict[str, Any], ai: Dict[str, Any], pricing_table: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    page = page_base("Investment Breakdown")
    page["controllers"] = [
        make_shape_controller(0, 0, 791, 860, "rgba(255,255,255,1)"),
        make_shape_controller(0, 0, 791, 5, "rgba(192,154,77,1)"),
        make_shape_controller(48, 28, 5, 38, "rgba(192,154,77,1)", 3),
        make_text_controller(66, 26, "660px", [heading_block("02  INVESTMENT BREAKDOWN", "h2", 18, "#1a1a2e")]),
        make_text_controller(48, 82, "695px", [text_block(ai.get("pricing_intro") or "Transparent cost breakdown with professional service tiers and contingency planning.", 13, "#666666")]),
        {
            "controllerId": uid(),
            "controllerName": "PRICING_TABLE",
            "x": 48,
            "y": 220,
            "style": {"width": 728, "height": "auto"},
            "header": pricing_table["header"],
            "content": pricing_table["content"],
            "value": pricing_table["summary"],
        },
        make_shape_controller(0, 856, 791, 4, "rgba(192,154,77,1)"),
    ]
    return page


def build_justification_page(ai: Dict[str, Any]) -> Dict[str, Any]:
    page = page_base("Pricing Justification")
    sections = ai.get("justification_sections") or []
    paragraph_blocks = [text_block(str(section), 13, "#333333") for section in sections if str(section).strip()]
    if not paragraph_blocks:
        paragraph_blocks = [text_block("Pricing justification will appear here.", 13, "#333333")]
    page["controllers"] = [
        make_shape_controller(0, 0, 791, 860, "rgba(255,255,255,1)"),
        make_shape_controller(0, 0, 791, 5, "rgba(192,154,77,1)"),
        make_shape_controller(48, 16, 5, 38, "rgba(192,154,77,1)", 3),
        make_text_controller(66, 14, "660px", [heading_block("03  PRICING JUSTIFICATION", "h2", 18, "#1a1a2e")]),
        make_text_controller(48, 84, "695px", [heading_block(ai.get("justification_title") or "Investment Breakdown & Value Framework", "h2", 32, "#0F172A")]),
        make_text_controller(48, 150, "695px", paragraph_blocks),
        make_shape_controller(0, 856, 791, 4, "rgba(192,154,77,1)"),
    ]
    return page


def build_acceptance_page(ai: Dict[str, Any], form_data: Dict[str, Any]) -> Dict[str, Any]:
    date_text = datetime.now().strftime("%d %B %Y")
    page = page_base("Acceptance & Authorisation")
    page["controllers"] = [
        make_shape_controller(0, 0, 791, 860, "rgba(15, 23, 42, 1)"),
        make_shape_controller(48, 200, 696, 1, "rgba(192,154,77,1)"),
        make_text_controller(48, 200, "696px", [heading_block("04  ACCEPTANCE & NEXT STEPS", "h2", 28, "#FFFFFF")]),
        make_text_controller(48, 280, "696px", [text_block(ai.get("acceptance_intro") or "By signing below, you authorize the project to proceed.", 13, "#E0E7FF")]),
        make_text_controller(48, 380, "696px", [heading_block("Client Signature", "h3", 14, "#FFFFFF")]),
        {"controllerId": uid(), "controllerName": "SIGNATURE", "x": 48, "y": 428, "signatureType": "CLIENT"},
        make_text_controller(48, 520, "696px", [heading_block("Administrator Signature", "h3", 14, "#FFFFFF")]),
        {"controllerId": uid(), "controllerName": "SIGNATURE", "x": 48, "y": 568, "signatureType": "ADMIN"},
        make_text_controller(48, 700, "696px", [text_block(f"Date: {date_text}", 12, "#9CA3AF")]),
        make_shape_controller(0, 780, 791, 4, "rgba(192,154,77,1)"),
    ]
    return page


def build_proposal(form_data: Dict[str, Any], ai: Dict[str, Any], pricing_table: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    return {
        "pages": [
            build_cover_page(form_data, ai),
            build_pricing_page(form_data, ai, pricing_table, currency_code),
            build_justification_page(ai),
            build_acceptance_page(ai, form_data),
        ],
        "macros": build_macros(form_data),
    }


@app.post("/api/v1/generate-proposal")
async def generate_proposal(request: Request):
    try:
        payload = await request.json()
        form_data = normalize_payload(payload if isinstance(payload, dict) else {})
        currency_code = ((form_data.get("meta") or {}).get("currency") or "USD").upper()

        pricing_table = build_pricing_table(form_data, currency_code)
        ai_content = call_digitalocean_ai(form_data, pricing_table, currency_code)
        result = build_proposal(form_data, ai_content, pricing_table, currency_code)
        return result
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error ({type(exc).__name__}): {str(exc)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("API_PORT", "8000")))
