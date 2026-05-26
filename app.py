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
import math
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
from fastapi.responses import StreamingResponse

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
    if isinstance(payload.get("data"), dict) and payload.get("success") is True:
        data = payload["data"]
        return {
            "formName": data.get("formName") or data.get("title") or "Proposal Form",
            "title": data.get("title") or data.get("formName") or "Proposal Form",
            "description": data.get("description") or "",
            "fields": data.get("fields") or [],
            "serviceTypes": data.get("serviceTypes") or [],
            "meta": payload.get("meta") or data.get("meta") or {},
            "responses": payload.get("responses") or data.get("responses") or {},
            "success": True,
        }

    if isinstance(payload.get("data"), dict):
        payload = {**payload["data"], "meta": payload.get("meta", payload["data"].get("meta"))}

    return {
        "formName": payload.get("formName") or payload.get("title") or "Proposal Form",
        "title": payload.get("title") or payload.get("formName") or "Proposal Form",
        "description": payload.get("description") or "",
        "fields": payload.get("fields") or payload.get("leadCapture", {}).get("fields") or [],
        "serviceTypes": payload.get("serviceTypes") or [],
        "meta": payload.get("meta") or {},
        "responses": payload.get("responses") or payload.get("answers") or {},
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
    w = f"{width}px" if isinstance(width, int) else width
    return {
        "controllerId": uid(),
        "controllerName": "TEXT",
        "style": {"width": w, "height": height},
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


def normalize_pricing_row(row: Any) -> List[str]:
    if not isinstance(row, (list, tuple)):
        row = [row]
    cells = list(row)[:3]
    while len(cells) < 3:
        cells.append("")

    name = str(cells[0]).strip()
    price_raw = re.sub(r"[^0-9.]", "", str(cells[1]))
    qty_raw = re.sub(r"[^0-9]", "", str(cells[2]))

    if not price_raw:
        price_raw = "0"
    if not qty_raw:
        qty_raw = "1"

    try:
        price_num = float(price_raw)
        price = str(int(price_num)) if price_num.is_integer() else f"{price_num:.2f}"
    except ValueError:
        price = "0"

    try:
        qty = str(int(float(qty_raw)))
    except ValueError:
        qty = "1"

    return [name, price, qty]


def estimate_pricing_table_height(row_count: int) -> int:
    return 35 + (row_count * 60)


def PTBL(
    x: int,
    y: int,
    content: List[List[Any]],
    header: Any = None,
    currency_code: str = "USD",
    summary: Dict[str, Any] = None,
) -> Dict[str, Any]:
    rows = [normalize_pricing_row(row) for row in (content or [])[:7] if row]
    header_rows = header or [
        {"value": "Name", "label": "Name"},
        {"value": "Price", "label": "Price"},
        {"value": "Quantity", "label": "Quantity"},
        {"value": "Subtotal", "label": "Subtotal"},
    ]
    if not isinstance(header_rows, list):
        header_rows = []

    def header_value(index: int, default: str) -> str:
        if index >= len(header_rows):
            return default
        cell = header_rows[index]
        if isinstance(cell, dict):
            return str(cell.get("value") or cell.get("label") or default)
        return str(cell or default)

    table_content: List[List[Dict[str, Any]]] = []
    for row_name, row_price, row_qty in rows:
        table_content.append([
            {
                "value": row_name,
                "style": {"width": 60, "height": 60},
            },
            {
                "value": row_price,
                "style": {"width": 60, "height": 60},
            },
            {
                "value": row_qty,
                "style": {"width": 60, "height": 60},
            },
        ])

    return {
        "controllerId": uid(),
        "controllerName": "PRICING_TABLE",
        "content": table_content,
        "header": [
            {"value": "Name", "label": "Name"},
            {"value": "Price", "label": "Price"},
            {"value": "Quantity", "label": "Quantity"},
            {"value": "Subtotal", "label": "Subtotal"},
        ],
        "style": {"width": 400},
        "x": x,
        "y": y,
        "rowHeights": [35],
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
        str(field.get("fieldName", "")).strip().lower()
        for field in form_data.get("fields", [])
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

    if any(name in field_names for name in ["fullname", "full name", "name"]):
        add("LEAD_NAME", "{LEAD_NAME}", "LEADS")
    if any("email" in name for name in field_names):
        add("LEAD_EMAIL", "{LEAD_EMAIL}", "LEADS")
    if any("phone" in name for name in field_names):
        add("LEAD_PHONE_NUMBER", "{LEAD_PHONE_NUMBER}", "LEADS")
    if any(name in field_names for name in ["projectlocation", "project location", "location", "city"]):
        add("LEAD_PROJECT_LOCATION", "{LEAD_PROJECT_LOCATION}", "LEADS")

    add("ORGANIZATION_NAME", "{ORGANIZATION_NAME}", "ORGANIZATION")
    add("CURRENT_DATE", "{CURRENT_DATE}", "COMMON", "date")
    return macros


def parse_services(form_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    services = form_data.get("serviceTypes", []) or []
    if isinstance(services, dict):
        services = services.get("fields", []) or []
    return [s for s in services if isinstance(s, dict) and s.get("isActive", True)]


def collect_priced_fields(form_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    priced_fields: List[Dict[str, Any]] = []

    for field in form_data.get("fields") or []:
        if isinstance(field, dict):
            priced_fields.append({"serviceName": "General", "field": field})

    for service in parse_services(form_data):
        service_name = str(service.get("serviceName") or "Service")
        for field in service.get("fields") or []:
            if isinstance(field, dict):
                priced_fields.append({"serviceName": service_name, "field": field})

    return priced_fields


def lookup_response_value(form_data: Dict[str, Any], field_name: str) -> Any:
    responses = form_data.get("responses") or form_data.get("answers") or {}
    if not isinstance(responses, dict):
        return None

    candidates = [field_name, field_name.lower(), field_name.replace(" ", "_"), field_name.replace(" ", "")]
    for candidate in candidates:
        if candidate in responses:
            return responses[candidate]
    return None


def normalize_option_index(value: Any) -> int:
    try:
        idx = int(value)
        return idx if idx >= 0 else 0
    except (TypeError, ValueError):
        return 0


def extract_price_from_matrix(field: Dict[str, Any], option_index: int = 0) -> float:
    price_matrix = field.get("priceMatrix") or {}
    if not isinstance(price_matrix, dict) or not price_matrix.get("enabled"):
        return 0.0

    entries = price_matrix.get("entries") or []
    if not entries:
        return 0.0

    idx = option_index if option_index < len(entries) else 0
    entry = entries[idx] or {}
    try:
        return float(entry.get("value", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def derive_quantity_from_text(text: str, default: float = 1.0) -> float:
    blob = str(text or "").lower()
    numbers = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*\.?\d*", blob)]
    if not numbers:
        return default
    if len(numbers) >= 2 and any(sep in blob for sep in ["-", " to ", "–", "—"]):
        return (numbers[0] + numbers[1]) / 2.0
    return numbers[0]


def infer_quantity_from_field(field: Dict[str, Any], response_value: Any = None, default: float = 1.0) -> float:
    field_type = str(field.get("type") or "").lower()
    unit_type = str(field.get("unitType") or "").lower()

    if response_value not in (None, ""):
        if isinstance(response_value, (int, float)):
            return float(response_value)
        return derive_quantity_from_text(str(response_value), default=default)

    if field_type == "number":
        return derive_quantity_from_text(
            f"{field.get('description', '')} {field.get('fieldName', '')}",
            default=default,
        )

    if unit_type in {"dimension", "quantity"}:
        return default

    return default


def derive_quantity_from_option_label(option_label: str, default: float = 1.0) -> float:
    text = str(option_label or "").lower()
    numbers = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*\.?\d*", text)]
    if not numbers:
        return default

    if "+" in text and numbers:
        return numbers[0]

    if len(numbers) >= 2 and any(sep in text for sep in ["-", " to ", "–", "—"]):
        return (numbers[0] + numbers[1]) / 2.0

    return numbers[0]


def extract_items(form_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for priced in collect_priced_fields(form_data):
        service_name = priced["serviceName"]
        field = priced["field"]

        price_matrix = field.get("priceMatrix") or {}
        if not isinstance(price_matrix, dict) or not price_matrix.get("enabled"):
            continue

        entries = price_matrix.get("entries") or []
        if not entries:
            continue

        field_type = str(field.get("type", "")).lower()
        options = field.get("options") or []
        response_value = lookup_response_value(form_data, field.get("fieldName", ""))

        selected_index = 0
        if isinstance(response_value, dict) and "optionIndex" in response_value:
            selected_index = normalize_option_index(response_value.get("optionIndex"))
        elif isinstance(response_value, (int, float)) and field_type in {"dropdown", "radio"}:
            selected_index = normalize_option_index(response_value)
        elif isinstance(response_value, str) and options:
            lowered = response_value.strip().lower()
            for idx, option in enumerate(options):
                if lowered == str(option.get("label", "")).strip().lower():
                    selected_index = idx
                    break

        if field_type in {"multiselect", "checkbox"}:
            pricing_rule = "additive_selection"
            selected_indices: List[int] = []
            if isinstance(response_value, list):
                if response_value and isinstance(response_value[0], (int, float)):
                    selected_indices = [normalize_option_index(v) for v in response_value]
                else:
                    option_lookup = {str(opt.get("label", "")).strip().lower(): i for i, opt in enumerate(options)}
                    selected_indices = [
                        option_lookup.get(str(v).strip().lower(), -1)
                        for v in response_value
                    ]
                    selected_indices = [i for i in selected_indices if i >= 0]
            if not selected_indices:
                selected_indices = [0]
            unit_price = sum(extract_price_from_matrix(field, idx) for idx in selected_indices)
            quantity = 1.0
        else:
            unit_price = extract_price_from_matrix(field, selected_index)
            quantity = infer_quantity_from_field(field, response_value=response_value, default=1.0)
            pricing_rule = "per_unit_measure" if field_type == "number" else "selected_option"

        if quantity <= 0:
            quantity = 1.0

        subtotal = float(unit_price) * float(quantity)
        display_name = str(field.get("fieldName") or field.get("description") or "Item").strip()
        item_label = display_name if service_name == "General" else f"{service_name}: {display_name}"
        summary = (
            f"Configured pricing rule '{pricing_rule}' applied to {item_label}; "
            f"unit price {unit_price:.2f}, quantity {quantity:g}, subtotal {subtotal:.2f}."
        )

        items.append(
            {
                "itemName": item_label,
                "category": service_name,
                "unitPrice": float(unit_price),
                "quantity": float(quantity),
                "subtotal": float(subtotal),
                "pricingRule": pricing_rule,
                "summary": summary,
                "justification": f"Configured pricing rule for {field.get('fieldName', 'selected field')}",
            }
        )
    return items


def build_pricing_table(form_data: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    items = extract_items(form_data)
    items = items[:7]
    subtotal = sum(item["subtotal"] for item in items)
    contingency = subtotal * 0.10
    total = subtotal + contingency

    content: List[List[str]] = []
    for item in items:
        content.append(
            [
                item["itemName"],
                str(int(item["unitPrice"])) if float(item["unitPrice"]).is_integer() else f"{float(item['unitPrice']):.2f}",
                str(int(item["quantity"])) if float(item["quantity"]).is_integer() else f"{float(item['quantity']):.2f}",
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
            {"value": "Name", "label": "Name"},
            {"value": "Price", "label": "Price"},
            {"value": "Quantity", "label": "Quantity"},
        ],
        "content": content,
        "items": items,
        "lineItemSummaries": [
            {
                "itemName": item["itemName"],
                "unitPrice": item["unitPrice"],
                "quantity": item["quantity"],
                "subtotal": item["subtotal"],
                "summary": item["summary"],
                "pricingRule": item["pricingRule"],
            }
            for item in items
        ],
        "summary": {
            "subtotal": subtotal,
            "contingency": contingency,
            "total": total,
            "currency": currency_code,
        },
        "justifications": justifications,
    }


PRICING_AI_KEYS = [
    "pricing_intro",
    "pricing_summary_note",
    "justification_title",
    "justification_sections",
    "line_item_notes",
]


def fallback_pricing_ai_content(form_data: Dict[str, Any], pricing_table: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    city = (form_data.get("meta") or {}).get("city") or "your project location"
    subtotal = money(pricing_table["summary"]["subtotal"], currency_code)
    contingency = money(pricing_table["summary"]["contingency"], currency_code)
    total = money(pricing_table["summary"]["total"], currency_code)
    line_items = pricing_table.get("lineItemSummaries") or []
    return {
        "pricing_intro": f"The pricing below has been tailored for {city} and reflects the selected scope, complexity, and delivery effort.",
        "pricing_summary_note": f"Subtotal {subtotal}, contingency reserve {contingency}, and total {total} are derived from the submitted service selections and pricing rules.",
        "justification_title": "Investment Breakdown & Value Framework",
        "justification_sections": [
            f"The subtotal of {subtotal} reflects the selected services and the effort needed to deliver the scope for {city}.",
            f"A contingency reserve of {contingency} protects against changes in scope, coordination, and site conditions.",
            f"The total investment of {total} includes the subtotal plus contingency, keeping the proposal financially clear and traceable.",
        ],
        "line_item_notes": [
            f"{item['itemName']}: {item['summary']}" for item in line_items
        ] or [
            "Line-item pricing follows the configured pricing rules in the submitted form.",
        ],
    }


def normalize_pricing_ai_content(ai_content: Any, form_data: Dict[str, Any], pricing_table: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    fallback = fallback_pricing_ai_content(form_data, pricing_table, currency_code)
    if not isinstance(ai_content, dict):
        return fallback

    normalized: Dict[str, Any] = {}
    for key in PRICING_AI_KEYS:
        value = ai_content.get(key, fallback.get(key))
        if key in {"justification_sections", "line_item_notes"}:
            if not isinstance(value, list):
                value = fallback[key]
            sections = [str(section).strip() for section in value if str(section).strip()]
            normalized[key] = sections or fallback[key]
        else:
            normalized[key] = str(value).strip() if value is not None else str(fallback.get(key, "")).strip()
    return normalized


def validate_pricing_ai_content_locally(ai_content: Dict[str, Any], form_data: Dict[str, Any], pricing_table: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    normalized = normalize_pricing_ai_content(ai_content, form_data, pricing_table, currency_code)
    fallback = fallback_pricing_ai_content(form_data, pricing_table, currency_code)
    city = ((form_data.get("meta") or {}).get("city") or "").strip()
    sections = normalized.get("justification_sections") or []

    issues: List[str] = []
    missing_fields: List[str] = []

    for key in PRICING_AI_KEYS:
        value = normalized.get(key)
        if key == "justification_sections":
            if not isinstance(value, list) or not value:
                missing_fields.append(key)
        elif not str(value).strip():
            missing_fields.append(key)

    if missing_fields:
        issues.append(f"Missing or empty fields: {', '.join(missing_fields)}")
    if len(sections) < 3:
        issues.append("Pricing justification should contain at least 3 sections.")

    section_blob = " ".join(str(section) for section in sections).lower()
    intro_blob = f"{normalized.get('pricing_intro', '')} {normalized.get('pricing_summary_note', '')}".lower()
    line_item_blob = " ".join(str(item) for item in (normalized.get("line_item_notes") or [])).lower()

    if "subtotal" not in section_blob and "subtotal" not in intro_blob:
        issues.append("Pricing content should mention subtotal.")
    if "contingency" not in section_blob and "contingency" not in intro_blob:
        issues.append("Pricing content should mention contingency.")
    if "total" not in section_blob and "total" not in intro_blob:
        issues.append("Pricing content should mention total.")
    if city and city.lower() not in section_blob and city.lower() not in intro_blob:
        issues.append("Pricing content should mention project location.")
    if pricing_table.get("lineItemSummaries") and len(normalized.get("line_item_notes") or []) < 1:
        issues.append("Pricing content should include at least one line-item note.")
    if "pricing rule" not in line_item_blob and "subtotal" not in line_item_blob and pricing_table.get("lineItemSummaries"):
        issues.append("Pricing content should explain the configured pricing rule for the line items.")

    approved = not issues
    corrected_content = normalized if approved else fallback
    score = 100 if approved else max(45, 100 - (len(issues) * 15))

    return {
        "approved": approved,
        "score": score,
        "response_validation": {
            "approved": approved,
            "issues": issues[:],
            "missing_fields": missing_fields,
        },
        "justification_validation": {
            "approved": approved and len(sections) >= 3,
            "issues": [issue for issue in issues if "Pricing content" in issue or "Pricing justification" in issue],
            "supported_points": [
                "Subtotal",
                "Contingency reserve",
                "Total amount",
                "Location context" if city else "Location context not provided",
                "Configured pricing rule" if pricing_table.get("lineItemSummaries") else "No line items",
            ],
            "unsupported_points": [],
        },
        "corrected_content": corrected_content,
        "summary": "Pricing content validated locally and repaired with deterministic fallback." if not approved else "Pricing content passed local validation.",
        "mode": "local-pricing-judge",
    }


def call_digitalocean_pricing_ai(form_data: Dict[str, Any], pricing_table: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    api_key = (
        os.getenv("DIGITALOCEAN_API_KEY")
        or os.getenv("DIGITALOCEAN_TOKEN")
        or os.getenv("MODEL_ACCESS_KEY")
        or ""
    ).strip()
    if not api_key:
        return fallback_pricing_ai_content(form_data, pricing_table, currency_code)

    base_url = os.getenv("DIGITALOCEAN_URL", "https://inference.do-ai.run").rstrip("/")
    model_name = os.getenv("DIGITALOCEAN_PRICING_MODEL") or os.getenv("DIGITALOCEAN_MODEL", "anthropic-claude-4.5-sonnet")
    endpoint = f"{base_url}/chat/completions" if base_url.endswith("/v1") else f"{base_url}/v1/chat/completions"

    prompt_payload = {
        "currency": currency_code,
        "city": (form_data.get("meta") or {}).get("city", ""),
        "pricingSummary": pricing_table.get("summary", {}),
        "pricingItems": pricing_table.get("lineItemSummaries", []),
        "pricingJustifications": pricing_table.get("justifications", {}),
        "pricingNarrativeRules": [
            "Write in a polished, architectural proposal tone.",
            "Explain why each major cost exists, not just what it is.",
            "Reference subtotal, contingency, and total explicitly.",
            "If line-item notes are available, keep them short and specific.",
            "Avoid generic filler such as 'this reflects the scope'.",
        ],
    }

    prompt = f"""
Return ONLY valid JSON with these keys:
pricing_intro, pricing_summary_note, justification_title, justification_sections, line_item_notes

This content is for the pricing page and pricing justification only.
It must explain the pricing summary using the provided subtotal, contingency, and total.
Do not change any numeric amounts.
Do not write generic marketing copy. Make it specific, grounded, and proposal-ready.
Each justification section should be 1-3 sentences long.
Each line item note should be 1 sentence and should explain the configured pricing rule or business reason.

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
                    {"role": "system", "content": "You are a proposal pricing writer that returns strict JSON only."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_completion_tokens": 900,
            },
            timeout=90,
        )
        if not response.ok:
            return fallback_pricing_ai_content(form_data, pricing_table, currency_code)
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        result = clean_json_text(content)
        if not isinstance(result, dict):
            return fallback_pricing_ai_content(form_data, pricing_table, currency_code)
        return normalize_pricing_ai_content(result, form_data, pricing_table, currency_code)
    except Exception:
        return fallback_pricing_ai_content(form_data, pricing_table, currency_code)


def call_digitalocean_pricing_judge(
    form_data: Dict[str, Any],
    pricing_table: Dict[str, Any],
    pricing_ai_content: Dict[str, Any],
    currency_code: str,
) -> Dict[str, Any]:
    api_key = (
        os.getenv("DIGITALOCEAN_API_KEY")
        or os.getenv("DIGITALOCEAN_TOKEN")
        or os.getenv("MODEL_ACCESS_KEY")
        or ""
    ).strip()
    if not api_key:
        return validate_pricing_ai_content_locally(pricing_ai_content, form_data, pricing_table, currency_code)

    base_url = os.getenv("DIGITALOCEAN_URL", "https://inference.do-ai.run").rstrip("/")
    model_name = (
        os.getenv("DIGITALOCEAN_PRICING_JUDGE_MODEL")
        or os.getenv("DIGITALOCEAN_JUDGE_MODEL")
        or os.getenv("DIGITALOCEAN_MODEL", "anthropic-claude-4.5-sonnet")
    )
    endpoint = f"{base_url}/chat/completions" if base_url.endswith("/v1") else f"{base_url}/v1/chat/completions"

    judge_payload = {
        "requiredKeys": PRICING_AI_KEYS,
        "currency": currency_code,
        "city": (form_data.get("meta") or {}).get("city", ""),
        "pricingSummary": pricing_table.get("summary", {}),
        "pricingItems": pricing_table.get("lineItemSummaries", []),
        "candidate": pricing_ai_content,
    }

    prompt = f"""
You are a strict judge for pricing narrative content.
Validate the candidate JSON against the pricing summary and row data.
Return ONLY valid JSON with these keys:
approved, score, response_validation, justification_validation, corrected_content, summary

Rules:
- response_validation must check for required keys and empty values.
- justification_validation must confirm subtotal, contingency, total, and location context when available.
- corrected_content must be a repaired JSON object with the required keys if anything is invalid.
- Do not use markdown.

Context:
{json.dumps(judge_payload, ensure_ascii=True)}
""".strip()

    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "You are a strict JSON-only validator for pricing narrative content."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "max_completion_tokens": 900,
            },
            timeout=90,
        )
        if not response.ok:
            return validate_pricing_ai_content_locally(pricing_ai_content, form_data, pricing_table, currency_code)

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        result = clean_json_text(content)
        if not isinstance(result, dict):
            return validate_pricing_ai_content_locally(pricing_ai_content, form_data, pricing_table, currency_code)

        corrected = normalize_pricing_ai_content(result.get("corrected_content") or pricing_ai_content, form_data, pricing_table, currency_code)
        response_validation = result.get("response_validation") if isinstance(result.get("response_validation"), dict) else {}
        justification_validation = result.get("justification_validation") if isinstance(result.get("justification_validation"), dict) else {}
        approved = bool(result.get("approved", False))

        if not approved:
            corrected = fallback_pricing_ai_content(form_data, pricing_table, currency_code)

        return {
            "approved": approved,
            "score": result.get("score", 0),
            "response_validation": {
                "approved": bool(response_validation.get("approved", approved)),
                "issues": response_validation.get("issues", []),
                "missing_fields": response_validation.get("missing_fields", []),
            },
            "justification_validation": {
                "approved": bool(justification_validation.get("approved", approved)),
                "issues": justification_validation.get("issues", []),
                "supported_points": justification_validation.get("supported_points", []),
                "unsupported_points": justification_validation.get("unsupported_points", []),
            },
            "corrected_content": corrected,
            "summary": str(result.get("summary", "")).strip() or "Pricing judge validation complete.",
            "mode": "llm-pricing-judge",
        }
    except Exception:
        return validate_pricing_ai_content_locally(pricing_ai_content, form_data, pricing_table, currency_code)


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
            f"Your investment of {money(pricing_table['summary']['subtotal'], currency_code)} covers all selected services including project management and quality assurance.",
            f"Location-specific factors for {city} have been incorporated into the pricing, including local regulatory compliance and regional construction standards.",
            f"A 10% contingency reserve of {contingency} is included as an industry-standard safeguard, bringing the total to {total}.",
        ],
        "acceptance_intro": "We're honored by the opportunity to bring your architectural vision to life. By signing below, you authorize us to commence work under the terms outlined in this proposal.",
    }


REQUIRED_AI_KEYS = [
    "title",
    "subtitle",
    "pricing_intro",
    "justification_title",
    "justification_sections",
    "acceptance_intro",
]


def normalize_ai_content(ai_content: Any, form_data: Dict[str, Any], pricing_table: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    fallback = fallback_ai_content(form_data, pricing_table, currency_code)
    if not isinstance(ai_content, dict):
        return fallback

    normalized: Dict[str, Any] = {}
    for key in REQUIRED_AI_KEYS:
        value = ai_content.get(key, fallback.get(key))
        if key == "justification_sections":
            if not isinstance(value, list):
                value = fallback["justification_sections"]
            sections = [str(section).strip() for section in value if str(section).strip()]
            normalized[key] = sections or fallback["justification_sections"]
        else:
            normalized[key] = str(value).strip() if value is not None else str(fallback.get(key, "")).strip()

    return normalized


def build_justification_text(pricing_table: Dict[str, Any]) -> List[Dict[str, str]]:
    justifications = pricing_table.get("justifications") or {}
    return [{"key": key, "text": str(value)} for key, value in justifications.items()]


def validate_ai_content_locally(ai_content: Dict[str, Any], form_data: Dict[str, Any], pricing_table: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    normalized = normalize_ai_content(ai_content, form_data, pricing_table, currency_code)
    fallback = fallback_ai_content(form_data, pricing_table, currency_code)
    city = ((form_data.get("meta") or {}).get("city") or "").strip()
    summary = pricing_table.get("summary") or {}
    sections = normalized.get("justification_sections") or []

    issues: List[str] = []
    missing_fields: List[str] = []

    for key in REQUIRED_AI_KEYS:
        value = normalized.get(key)
        if key == "justification_sections":
            if not isinstance(value, list) or not value:
                missing_fields.append(key)
        elif not str(value).strip():
            missing_fields.append(key)

    if missing_fields:
        issues.append(f"Missing or empty fields: {', '.join(missing_fields)}")

    if len(sections) < 3:
        issues.append("Justification should contain at least 3 sections.")

    section_blob = " ".join(str(section) for section in sections).lower()
    title_blob = f"{normalized.get('pricing_intro', '')} {normalized.get('acceptance_intro', '')}".lower()

    if "subtotal" not in section_blob and "subtotal" not in title_blob:
        issues.append("Justification should explain the subtotal basis.")
    if "contingency" not in section_blob and "contingency" not in title_blob:
        issues.append("Justification should explain the contingency reserve.")
    if city and city.lower() not in section_blob and city.lower() not in title_blob:
        issues.append("Justification should mention the project location.")
    if summary:
        total_text = money(float(summary.get("total", 0) or 0), currency_code).lower()
        subtotal_text = money(float(summary.get("subtotal", 0) or 0), currency_code).lower()
        if subtotal_text not in section_blob and subtotal_text not in title_blob:
            issues.append("Justification should reference the subtotal amount.")
        if total_text not in section_blob and total_text not in title_blob:
            issues.append("Justification should reference the total amount.")

    approved = not issues
    corrected_content = normalized if approved else fallback
    score = 100 if approved else max(45, 100 - (len(issues) * 15))

    return {
        "approved": approved,
        "score": score,
        "response_validation": {
            "approved": approved,
            "issues": issues[:],
            "missing_fields": missing_fields,
        },
        "justification_validation": {
            "approved": approved and len(sections) >= 3,
            "issues": [issue for issue in issues if "Justification" in issue],
            "supported_points": [
                "Subtotal",
                "Contingency reserve",
                "Location context" if city else "Location context not provided",
                "Total amount",
            ],
            "unsupported_points": [],
        },
        "corrected_content": corrected_content,
        "summary": "Content validated locally and repaired with deterministic fallback." if not approved else "Content passed local validation.",
        "mode": "local-judge",
    }


def call_digitalocean_judge(
    form_data: Dict[str, Any],
    pricing_table: Dict[str, Any],
    ai_content: Dict[str, Any],
    currency_code: str,
) -> Dict[str, Any]:
    api_key = (
        os.getenv("DIGITALOCEAN_API_KEY")
        or os.getenv("DIGITALOCEAN_TOKEN")
        or os.getenv("MODEL_ACCESS_KEY")
        or ""
    ).strip()
    if not api_key:
        return validate_ai_content_locally(ai_content, form_data, pricing_table, currency_code)

    base_url = os.getenv("DIGITALOCEAN_URL", "https://inference.do-ai.run").rstrip("/")
    model_name = (
        (form_data.get("meta") or {}).get("judgeModel")
        or os.getenv("DIGITALOCEAN_JUDGE_MODEL")
        or os.getenv("DIGITALOCEAN_MODEL", "anthropic-claude-4.5-sonnet")
    )
    endpoint = f"{base_url}/chat/completions" if base_url.endswith("/v1") else f"{base_url}/v1/chat/completions"

    judge_payload = {
        "requiredKeys": REQUIRED_AI_KEYS,
        "currency": currency_code,
        "city": (form_data.get("meta") or {}).get("city", ""),
        "pricingSummary": pricing_table.get("summary", {}),
        "pricingJustifications": pricing_table.get("justifications", {}),
        "candidate": ai_content,
    }

    prompt = f"""
You are a strict judge for proposal content.
Validate the candidate JSON against the pricing summary and justification rules.
Return ONLY valid JSON with these keys:
approved, score, response_validation, justification_validation, corrected_content, summary

Rules:
- response_validation must check for required keys and empty values.
- justification_validation must confirm the justification explains subtotal, total, contingency, and location context when available.
- corrected_content must be a repaired JSON object with the required keys if anything is invalid.
- Do not use markdown.

Context:
{json.dumps(judge_payload, ensure_ascii=True)}
""".strip()

    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "You are a strict JSON-only validator for proposal content."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "max_completion_tokens": 1200,
            },
            timeout=90,
        )
        if not response.ok:
            return validate_ai_content_locally(ai_content, form_data, pricing_table, currency_code)

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        result = clean_json_text(content)
        if not isinstance(result, dict):
            return validate_ai_content_locally(ai_content, form_data, pricing_table, currency_code)

        corrected = normalize_ai_content(result.get("corrected_content") or ai_content, form_data, pricing_table, currency_code)
        response_validation = result.get("response_validation") if isinstance(result.get("response_validation"), dict) else {}
        justification_validation = result.get("justification_validation") if isinstance(result.get("justification_validation"), dict) else {}
        approved = bool(result.get("approved", False))

        if not approved:
            corrected = fallback_ai_content(form_data, pricing_table, currency_code)

        return {
            "approved": approved,
            "score": result.get("score", 0),
            "response_validation": {
                "approved": bool(response_validation.get("approved", approved)),
                "issues": response_validation.get("issues", []),
                "missing_fields": response_validation.get("missing_fields", []),
            },
            "justification_validation": {
                "approved": bool(justification_validation.get("approved", approved)),
                "issues": justification_validation.get("issues", []),
                "supported_points": justification_validation.get("supported_points", []),
                "unsupported_points": justification_validation.get("unsupported_points", []),
            },
            "corrected_content": corrected,
            "summary": str(result.get("summary", "")).strip() or "Judge validation complete.",
            "mode": "llm-judge",
        }
    except Exception:
        return validate_ai_content_locally(ai_content, form_data, pricing_table, currency_code)


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
    table_controller = PTBL(
        161.6875, 218.625,
        pricing_table["content"],
        pricing_table.get("header"),
        currency_code,
        pricing_table.get("summary"),
    )
    page["controllers"] = [
        make_shape_controller(0, 0, 792, 1120, "rgba(255,255,255,1)"),
        make_shape_controller(0, 0, 792, 6, "rgba(192,154,77,1)"),
        {
            "controllerId": uid(),
            "controllerName": "ORGANIZATION_LOGO",
            "style": {"width": "130px", "height": "44px"},
            "x": 48,
            "y": 24,
            "value": "",
        },
        make_text_controller(48, 80, "696px", [heading_block("02  INVESTMENT BREAKDOWN", "h2", 18, "#0F172A")]),
        make_text_controller(48, 130, "696px", [text_block(ai.get("pricing_intro") or "Transparent cost breakdown with professional service tiers.", 13, "#333333")]),
        table_controller,
        make_shape_controller(0, 1112, 792, 8, "rgba(192,154,77,1)"),
    ]
    return page


def build_justification_page(ai: Dict[str, Any]) -> Dict[str, Any]:
    page = page_base("Pricing Justification")
    sections = ai.get("justification_sections") or []
    line_item_notes = ai.get("line_item_notes") or []
    controllers: List[Dict[str, Any]] = [
        make_shape_controller(0, 0, 792, 1120, "rgba(255,255,255,1)"),
        make_shape_controller(0, 0, 792, 6, "rgba(192,154,77,1)"),
        {
            "controllerId": uid(),
            "controllerName": "ORGANIZATION_LOGO",
            "style": {"width": "130px", "height": "44px"},
            "x": 48,
            "y": 24,
            "value": "",
        },
        make_text_controller(48, 80, "696px", [heading_block("03  PRICING JUSTIFICATION", "h2", 18, "#0F172A")]),
        make_text_controller(48, 130, "696px", [heading_block(ai.get("justification_title") or "Investment Breakdown & Value Framework", "h2", 28, "#0F172A")]),
    ]

    import math

    current_y = 200
    for section in sections:
        section_text = str(section).strip()
        if not section_text:
            continue
        lines = math.ceil(len(section_text) / 90)
        approx_height = lines * 22
        controllers.append(
            make_text_controller(
                48,
                current_y,
                "696px",
                [text_block(section_text, 13, "#333333")],
            )
        )
        current_y += approx_height + 24

    if line_item_notes:
        controllers.append(make_text_controller(48, current_y + 12, "696px", [heading_block("Line Item Rationale", "h3", 16, "#0F172A")]))
        current_y += 56
        for note in line_item_notes:
            note_text = str(note).strip()
            if not note_text:
                continue
            lines = math.ceil(len(note_text) / 88)
            approx_height = max(24, lines * 20)
            controllers.append(
                make_text_controller(
                    48,
                    current_y,
                    "696px",
                    [text_block(note_text, 12, "#4B5563")],
                )
            )
            current_y += approx_height + 16

    controllers.append(make_shape_controller(0, 1112, 792, 8, "rgba(192,154,77,1)"))
    page["controllers"] = controllers
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
        make_divider(48, 420, 300),
        {"controllerId": uid(), "controllerName": "SIGNATURE", "x": 48, "y": 428, "signatureType": "CLIENT"},
        make_text_controller(48, 520, "696px", [heading_block("Administrator Signature", "h3", 14, "#FFFFFF")]),
        make_divider(48, 560, 300),
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


def build_full_proposal_response(form_data: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    pricing_table = build_pricing_table(form_data, currency_code)
    pricing_ai_content = call_digitalocean_pricing_ai(form_data, pricing_table, currency_code)
    pricing_judge_report = call_digitalocean_pricing_judge(form_data, pricing_table, pricing_ai_content, currency_code)
    proposal_ai_content = call_digitalocean_ai(form_data, pricing_table, currency_code)
    pricing_ai_merged = normalize_pricing_ai_content(
        pricing_judge_report.get("corrected_content") or pricing_ai_content,
        form_data,
        pricing_table,
        currency_code,
    )
    ai_content = {**proposal_ai_content, **pricing_ai_merged}
    judge_report = call_digitalocean_judge(form_data, pricing_table, ai_content, currency_code)
    validated_ai_content = normalize_ai_content(
        judge_report.get("corrected_content") or ai_content,
        form_data,
        pricing_table,
        currency_code,
    )

    result = build_proposal(form_data, validated_ai_content, pricing_table, currency_code)
    result["pricingTable"] = pricing_table
    result["lineItemSummaries"] = pricing_table.get("lineItemSummaries", [])
    result["justificationText"] = build_justification_text(pricing_table)
    result["pricingValidation"] = {
        "approved": pricing_judge_report.get("approved", False),
        "score": pricing_judge_report.get("score", 0),
        "mode": pricing_judge_report.get("mode", "local-pricing-judge"),
        "response_validation": pricing_judge_report.get("response_validation", {}),
        "justification_validation": pricing_judge_report.get("justification_validation", {}),
        "summary": pricing_judge_report.get("summary", ""),
    }
    result["validation"] = {
        "approved": judge_report.get("approved", False),
        "score": judge_report.get("score", 0),
        "mode": judge_report.get("mode", "local-judge"),
        "response_validation": judge_report.get("response_validation", {}),
        "justification_validation": judge_report.get("justification_validation", {}),
        "summary": judge_report.get("summary", ""),
    }
    return result


@app.post("/api/v1/generate-proposal")
async def generate_proposal(request: Request):
    try:
        payload = await request.json()
        form_data = normalize_payload(payload if isinstance(payload, dict) else {})
        currency_code = ((form_data.get("meta") or {}).get("currency") or "USD").upper()
        return build_full_proposal_response(form_data, currency_code)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error ({type(exc).__name__}): {str(exc)}")


@app.post("/api/v1/generate-proposal/stream")
async def generate_proposal_stream(request: Request):
    try:
        payload = await request.json()
        form_data = normalize_payload(payload if isinstance(payload, dict) else {})
        currency_code = ((form_data.get("meta") or {}).get("currency") or "USD").upper()

        def sse(event: str, data: Any) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=True)}\n\n"

        def iterator():
            yield sse("start", {"status": "started", "currency": currency_code})
            yield sse("stage", {"name": "pricing", "status": "running"})
            pricing_table = build_pricing_table(form_data, currency_code)
            yield sse("stage", {"name": "pricing", "status": "done", "summary": pricing_table.get("summary", {})})

            yield sse("stage", {"name": "pricing_ai", "status": "running"})
            pricing_ai_content = call_digitalocean_pricing_ai(form_data, pricing_table, currency_code)
            yield sse("stage", {"name": "pricing_ai", "status": "done", "content": pricing_ai_content})

            yield sse("stage", {"name": "pricing_judge", "status": "running"})
            pricing_judge_report = call_digitalocean_pricing_judge(form_data, pricing_table, pricing_ai_content, currency_code)
            yield sse("stage", {"name": "pricing_judge", "status": "done", "validation": pricing_judge_report})

            yield sse("stage", {"name": "proposal_ai", "status": "running"})
            proposal_ai_content = call_digitalocean_ai(form_data, pricing_table, currency_code)
            yield sse("stage", {"name": "proposal_ai", "status": "done", "content": proposal_ai_content})

            pricing_ai_merged = normalize_pricing_ai_content(
                pricing_judge_report.get("corrected_content") or pricing_ai_content,
                form_data,
                pricing_table,
                currency_code,
            )
            ai_content = {**proposal_ai_content, **pricing_ai_merged}

            yield sse("stage", {"name": "judge", "status": "running"})
            judge_report = call_digitalocean_judge(form_data, pricing_table, ai_content, currency_code)
            yield sse("stage", {"name": "judge", "status": "done", "validation": judge_report})

            validated_ai_content = normalize_ai_content(
                judge_report.get("corrected_content") or ai_content,
                form_data,
                pricing_table,
                currency_code,
            )
            result = build_proposal(form_data, validated_ai_content, pricing_table, currency_code)
            result["pricingTable"] = pricing_table
            result["lineItemSummaries"] = pricing_table.get("lineItemSummaries", [])
            result["justificationText"] = build_justification_text(pricing_table)
            result["pricingValidation"] = {
                "approved": pricing_judge_report.get("approved", False),
                "score": pricing_judge_report.get("score", 0),
                "mode": pricing_judge_report.get("mode", "local-pricing-judge"),
                "response_validation": pricing_judge_report.get("response_validation", {}),
                "justification_validation": pricing_judge_report.get("justification_validation", {}),
                "summary": pricing_judge_report.get("summary", ""),
            }
            result["validation"] = {
                "approved": judge_report.get("approved", False),
                "score": judge_report.get("score", 0),
                "mode": judge_report.get("mode", "local-judge"),
                "response_validation": judge_report.get("response_validation", {}),
                "justification_validation": judge_report.get("justification_validation", {}),
                "summary": judge_report.get("summary", ""),
            }
            yield sse("result", result)
            yield sse("done", {"status": "completed"})

        return StreamingResponse(iterator(), media_type="text/event-stream")
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error ({type(exc).__name__}): {str(exc)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("API_PORT", "8000")))
