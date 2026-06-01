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

"""
IntoAEC AI Lead Capture Form Generator — FastAPI application.

Set env vars (see .env.example), then run:
  uvicorn app:app --reload --port 8000

Example:
  curl -N -X POST http://localhost:8000/lead-capture-with-ai \\
    -H "Content-Type: application/json" \\
    -H "Accept: text/event-stream" \\
    -d '{"prompt":"...","organizationDetails":"...","serviceTypes":["Architecture"],"location":{"country":"IN","city":"Chennai"}}'

  Non-streaming JSON: POST .../lead-capture-with-ai/sync
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))

app = FastAPI(title="IntoAEC AI Lead Capture Form Generator", version="1.0.0")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "INVALID_INPUT",
            "message": "Request validation failed",
            "details": exc.errors(),
        },
    )


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}



def uid() -> str:
    return str(uuid4())


def now_ms() -> str:
    return str(int(datetime.now().timestamp() * 1000))


def normalize_price_matrix(price_matrix: Any, enabled_fallback: Any = None) -> Dict[str, Any]:
    if isinstance(price_matrix, dict):
        normalized = dict(price_matrix)
        normalized["enabled"] = bool(normalized.get("enabled", enabled_fallback))
        normalized["entries"] = normalized.get("entries") or []
        return normalized

    return {
        "enabled": bool(enabled_fallback),
        "entries": [],
    }


def response_row_to_field(row: Dict[str, Any]) -> Dict[str, Any]:
    answer = row.get("answer")
    return {
        "fieldId": row.get("fieldId"),
        "formFieldId": row.get("formFieldId"),
        "sourceItemId": row.get("sourceItemId"),
        "serviceTypeId": row.get("serviceTypeId"),
        "fieldName": row.get("fieldName") or row.get("description") or row.get("fieldId") or "Field",
        "description": row.get("description") or "",
        "type": row.get("typeKey") or row.get("type") or "text",
        "typeKey": row.get("typeKey") or row.get("type") or "text",
        "unitType": row.get("unitType"),
        "options": row.get("options") or [],
        "priceMatrix": normalize_price_matrix(row.get("priceMatrix"), row.get("priceMatrix", {}).get("enabled") if isinstance(row.get("priceMatrix"), dict) else False),
        "answer": answer,
        "value": answer,
        "enabled": True,
    }


def normalize_response_rows(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        if isinstance(value.get("responses"), list):
            return [row for row in value["responses"] if isinstance(row, dict)]
        if isinstance(value.get("answers"), list):
            return [row for row in value["answers"] if isinstance(row, dict)]
    return []


def normalize_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, list):
        responses = normalize_response_rows(payload)
        fields = [response_row_to_field(row) for row in responses]
        return {
            "formName": "Proposal Form",
            "title": "Proposal Form",
            "description": "",
            "fields": fields,
            "serviceTypes": [],
            "meta": {},
            "responses": responses,
            "success": True,
        }

    if not isinstance(payload, dict):
        payload = {}

    if isinstance(payload.get("data"), dict) and payload.get("success") is True:
        data = payload["data"]
        responses = normalize_response_rows(
            payload.get("responses")
            or payload.get("answers")
            or payload.get("fieldResponses")
            or data.get("responses")
            or data.get("answers")
            or data.get("fieldResponses")
            or {}
        )
        fields = data.get("fields") or [response_row_to_field(row) for row in responses]
        return {
            "formName": data.get("formName") or data.get("title") or "Proposal Form",
            "title": data.get("title") or data.get("formName") or "Proposal Form",
            "description": data.get("description") or "",
            "fields": fields,
            "serviceTypes": data.get("serviceTypes") or [],
            "meta": payload.get("meta") or data.get("meta") or {},
            "responses": responses or payload.get("responses") or payload.get("answers") or payload.get("fieldResponses") or {},
            "success": True,
        }

    if isinstance(payload.get("data"), dict):
        payload = {**payload["data"], "meta": payload.get("meta", payload["data"].get("meta"))}

    responses = normalize_response_rows(
        payload.get("responses")
        or payload.get("answers")
        or payload.get("fieldResponses")
        or {}
    )
    fields = payload.get("fields") or payload.get("leadCapture", {}).get("fields") or []
    if not fields and responses:
        fields = [response_row_to_field(row) for row in responses]

    return {
        "formName": payload.get("formName") or payload.get("title") or "Proposal Form",
        "title": payload.get("title") or payload.get("formName") or "Proposal Form",
        "description": payload.get("description") or "",
        "fields": fields,
        "serviceTypes": payload.get("serviceTypes") or [],
        "meta": payload.get("meta") or {},
        "responses": responses or payload.get("responses") or payload.get("answers") or payload.get("fieldResponses") or {},
    }


def parse_raw_request_body(raw: bytes) -> Any:
    text = raw.decode("utf-8-sig", errors="strict")
    # Normalize Unicode whitespace that often appears when JSON is copy/pasted
    # from chat apps, browsers, or rich text editors.
    text = text.replace("\ufeff", "")
    text = text.replace("\u00a0", " ").replace("\u2007", " ").replace("\u202f", " ")
    text = text.strip()
    if not text:
        return None
    return json.loads(text)


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
        if isinstance(row, dict):
            row = [
                row.get("name") or row.get("itemName") or row.get("label") or row.get("title") or "",
                row.get("price") or row.get("unitPrice") or row.get("rate") or "",
                row.get("quantity") or row.get("qty") or row.get("amount") or "",
            ]
        else:
            row = [row]
    cells = list(row)[:3]
    while len(cells) < 3:
        cells.append("")

    name = str(cells[0]).strip()
    price_raw = re.sub(r"[^0-9.]", "", str(cells[1]))
    qty_raw = re.sub(r"[^0-9.]", "", str(cells[2]))

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
    rows = [normalize_pricing_row(row) for row in (content or [])[:8] if row]
    header_rows = header or [
        {"value": "Name", "label": "Name"},
        {"value": "Price", "label": "Price"},
        {"value": "Quantity", "label": "Quantity"},
        {"value": "Subtotal", "label": "Subtotal"},
    ]
    if not isinstance(header_rows, list):
        header_rows = []

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
        "header": header_rows,
        "style": {"width": "764px", "height": f"{35 + (len(table_content) * 35)}px"},
        "x": x,
        "y": y,
        "rowHeights": [35 for _ in table_content] or [35],
    }


def infer_pricing_quantity(form_data: Dict[str, Any]) -> float:
    for priced in collect_priced_fields(form_data):
        field = priced["field"]
        if not is_quantity_pricing_field(field):
            continue
        field_name = str(field.get("fieldName") or "").strip()
        response_value = lookup_response_value(form_data, field_name)
        if response_value in (None, "", [], {}):
            continue
        quantity = infer_quantity_from_field(field, response_value, default=1.0)
        if quantity > 0:
            return quantity
    return 1.0


def project_context_for_pricing(form_data: Dict[str, Any]) -> Dict[str, Any]:
    meta = form_data.get("meta") or {}
    project_type = str(lookup_response_value(form_data, "Project Type") or lookup_response_value(form_data, "projectType") or "").strip()
    quantity = infer_pricing_quantity(form_data)

    selection_map: Dict[str, str] = {}
    for selection in extract_user_selections(form_data):
        question = str(selection.get("question") or "").strip().lower()
        answer = str(selection.get("answer") or "").strip()
        if question and answer:
            selection_map[question] = answer

    selected_services = [str(s.get("serviceName") or "").strip() for s in parse_services(form_data) if str(s.get("serviceName") or "").strip()]
    selected_answers = [str(item.get("answer") or "").strip() for item in extract_user_selections(form_data) if str(item.get("answer") or "").strip()]

    return {
        "city": str(meta.get("city") or "").strip(),
        "projectType": project_type,
        "projectTypeLower": project_type.lower(),
        "quantity": quantity,
        "quantityText": str(int(quantity)) if float(quantity).is_integer() else f"{float(quantity):.2f}",
        "selectedServices": selected_services,
        "selectedAnswers": selected_answers,
        "selectionMap": selection_map,
    }


def pricing_phase_rows_from_context(context: Dict[str, Any]) -> List[List[str]]:
    quantity_text = str(context.get("quantityText") or "1")
    project_type = str(context.get("projectType") or "").lower()
    selection_map = context.get("selectionMap") or {}
    target_space = ""
    for key, value in selection_map.items():
        blob = key.lower()
        if any(term in blob for term in ["which areas", "areas need", "room", "space", "interior"]):
            target_space = str(value or "").strip()
            break
    if not target_space:
        for value in context.get("selectedAnswers") or []:
            if str(value).strip():
                target_space = str(value).strip()
                break

    answers = " | ".join(
        [
            str(context.get("projectType") or "").strip(),
            str(context.get("city") or "").strip(),
            " ".join(context.get("selectedServices") or []),
            " ".join(context.get("selectedAnswers") or []),
        ]
    ).lower()

    if any(term in project_type for term in ["commercial", "office", "retail", "workspace"]):
        phase_rows = [
            "Site Assessment & Requirement Study",
            "Concept Design & Space Planning",
            "Detailed Drawings & Documentation",
            "BOQ & Cost Estimation",
            "Civil / Structural Coordination",
            "MEP Services Coordination",
            "Interior Finishes & Material Selection",
            "Project Management & Client Coordination",
        ]
        factors = ["1", "3", "4", "1.5", "3", "2.50", "2", "2"]
    elif any(term in answers for term in ["bedroom", "living room", "kitchen", "interior"]):
        phase_rows = [
            "Room Survey & Layout Verification",
            "Concept Design & Space Planning",
            "Furniture / Joinery Design",
            "Material & Finish Selection",
            "BOQ & Cost Estimation",
            "MEP / Lighting Coordination",
            "Execution Drawings & Detailing",
            "Project Management & Revision Support",
        ]
        factors = ["1", "3", "2", "2", "1.5", "2.50", "4", "2"]
    else:
        phase_rows = [
            "Site Assessment & Requirement Study",
            "Concept Design & Space Planning",
            "Detailed Drawings & Documentation",
            "BOQ & Cost Estimation",
            "Technical Coordination & Compliance",
            "Material Review & Selection",
            "Project Management & Client Coordination",
            "Final Proposal & Revision Support",
        ]
        factors = ["1", "2.50", "3", "1.50", "2", "2", "2", "1"]

    # Add a tiny amount of personalization to the phase names if the user answered clearly.
    city = str(context.get("city") or "").strip()
    if target_space:
        phase_rows[0] = f"{phase_rows[0]} - {target_space}"
        phase_rows[1] = f"{phase_rows[1]} for {target_space}"
        phase_rows[6] = f"{phase_rows[6]} - {target_space}"
    if city:
        phase_rows[0] = f"{phase_rows[0]} - {city}"

    return [[name, factor, quantity_text] for name, factor in zip(phase_rows[:8], factors[:8])]


def fallback_pricing_table_rows(form_data: Dict[str, Any], pricing_table: Dict[str, Any], currency_code: str) -> List[List[str]]:
    return pricing_phase_rows_from_context(project_context_for_pricing(form_data))


def normalize_pricing_table_rows(rows: Any) -> List[List[str]]:
    if not isinstance(rows, list):
        return []

    normalized: List[List[str]] = []
    for row in rows[:8]:
        if isinstance(row, dict):
            normalized.append(
                normalize_pricing_row(
                    [
                        row.get("name") or row.get("itemName") or row.get("label") or row.get("title") or "",
                        row.get("price") or row.get("unitPrice") or row.get("rate") or "",
                        row.get("quantity") or row.get("qty") or row.get("amount") or "",
                    ]
                )
            )
        elif isinstance(row, (list, tuple)):
            normalized.append(normalize_pricing_row(list(row)))
        else:
            normalized.append(normalize_pricing_row([row, "", ""]))

    return [row for row in normalized if any(str(cell).strip() for cell in row)]


def apply_ai_pricing_table_rows(
    pricing_table: Dict[str, Any],
    pricing_ai_content: Dict[str, Any],
    form_data: Dict[str, Any],
    currency_code: str,
) -> Dict[str, Any]:
    updated = dict(pricing_table)
    rows = normalize_pricing_table_rows((pricing_ai_content or {}).get("pricing_table_rows"))
    if not rows:
        rows = fallback_pricing_table_rows(form_data, pricing_table, currency_code)
    updated["calculationContent"] = pricing_table.get("calculationContent") or pricing_table.get("content") or []
    updated["content"] = rows
    updated["aiGeneratedPricingTable"] = rows
    return updated


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


def field_display_name(field: Dict[str, Any]) -> str:
    label = str(field.get("description") or field.get("fieldName") or "Item").strip()
    return label or "Item"


def option_label(field: Dict[str, Any], option_index: int) -> str:
    options = field.get("options") or []
    if option_index < 0 or option_index >= len(options):
        return ""
    option = options[option_index]
    if isinstance(option, dict):
        return str(option.get("label") or option.get("value") or option.get("name") or "").strip()
    return str(option or "").strip()


def answer_text_for_field(field: Dict[str, Any], response_value: Any, selected_indices: List[int]) -> str:
    field_type = str(field.get("type") or "").lower()
    options = field.get("options") or []

    if isinstance(response_value, dict):
        for key in ["label", "value", "answer", "response", "selectedValue", "text"]:
            value = response_value.get(key)
            if value not in (None, ""):
                return str(value).strip()
        if selected_indices:
            labels = [option_label(field, idx) for idx in selected_indices]
            labels = [label for label in labels if label]
            if labels:
                return ", ".join(labels)
        return ""

    if isinstance(response_value, list):
        labels: List[str] = []
        for value in response_value:
            if isinstance(value, (int, float)):
                label = option_label(field, normalize_option_index(value))
                if label:
                    labels.append(label)
                continue
            lowered = str(value).strip()
            matched = ""
            for idx, option in enumerate(options):
                option_text = str(option.get("label") or option.get("value") or option.get("name") or "").strip()
                if lowered and lowered.lower() == option_text.lower():
                    matched = option_text
                    break
            labels.append(matched or lowered)
        labels = [label for label in labels if label]
        return ", ".join(labels)

    if selected_indices:
        labels = [option_label(field, idx) for idx in selected_indices]
        labels = [label for label in labels if label]
        if labels:
            return ", ".join(labels)

    if response_value in (None, ""):
        return ""

    if field_type in {"number", "dimension"} and isinstance(response_value, (int, float)):
        return str(response_value)

    return str(response_value).strip()


def is_generic_field_label(label: str) -> bool:
    blob = str(label or "").strip().lower()
    if not blob:
        return True
    generic_terms = {
        "area",
        "budget",
        "cost",
        "details",
        "dimension",
        "email",
        "name",
        "notes",
        "phone",
        "price",
        "project",
        "quantity",
        "requirements",
        "size",
        "style",
        "timeline",
        "value",
    }
    if blob in generic_terms:
        return True
    return len(blob.split()) <= 2 and any(term in blob for term in generic_terms)


def format_answer_aware_item_name(field: Dict[str, Any], response_value: Any, selected_indices: List[int]) -> str:
    label = field_display_name(field)
    answer_text = answer_text_for_field(field, response_value, selected_indices)
    if answer_text and answer_text.lower() != label.lower():
        if is_generic_field_label(label):
            return answer_text
        return f"{label}: {answer_text}"
    return label


def lookup_response_value(form_data: Dict[str, Any], field_name: str) -> Any:
    def canonical(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(s or "").strip().lower())

    def tokens(s: str) -> List[str]:
        stop = {"what", "is", "the", "your", "in", "of", "and", "or", "for"}
        return [t for t in re.findall(r"[a-z0-9]+", str(s or "").strip().lower()) if t not in stop]

    def fuzzy_same(a: str, b: str) -> bool:
        if not a or not b:
            return False
        ca, cb = canonical(a), canonical(b)
        if ca == cb or ca in cb or cb in ca:
            return True
        ta, tb = set(tokens(a)), set(tokens(b))
        if not ta or not tb:
            return False
        inter = ta & tb
        return len(inter) >= max(2, min(len(ta), len(tb)) - 1)

    responses = form_data.get("responses") or form_data.get("answers") or {}
    if isinstance(responses, list):
        target = canonical(field_name)
        for row in responses:
            if not isinstance(row, dict):
                continue
            row_keys = [
                row.get("fieldName"),
                row.get("description"),
                row.get("name"),
                row.get("key"),
                row.get("fieldId"),
                row.get("formFieldId"),
                row.get("sourceItemId"),
            ]
            if any(canonical(key) == target for key in row_keys if key):
                for value_key in ["value", "answer", "response", "selected", "selectedValue"]:
                    if value_key in row:
                        return row[value_key]
        return None

    if not isinstance(responses, dict):
        responses = {}

    candidates = [field_name, field_name.lower(), field_name.replace(" ", "_"), field_name.replace(" ", "")]
    for candidate in candidates:
        if candidate in responses:
            return responses[candidate]
    for key, value in responses.items():
        if fuzzy_same(str(key), field_name):
            return value

    # Field-level fallback when a value is embedded in the field object itself.
    for field in form_data.get("fields") or []:
        if not isinstance(field, dict):
            continue
        if str(field.get("fieldName") or "").strip().lower() != field_name.strip().lower():
            continue
        for value_key in ["value", "answer", "response", "selectedValue", "inputValue"]:
            if value_key in field and field.get(value_key) not in (None, ""):
                return field.get(value_key)

    for service in form_data.get("serviceTypes") or []:
        if not isinstance(service, dict):
            continue
        for field in service.get("fields") or []:
            if not isinstance(field, dict):
                continue
            if str(field.get("fieldName") or "").strip().lower() != field_name.strip().lower():
                continue
            for value_key in ["value", "answer", "response", "selectedValue", "inputValue"]:
                if value_key in field and field.get(value_key) not in (None, ""):
                    return field.get(value_key)
    return None


def normalize_option_index(value: Any) -> int:
    try:
        idx = int(value)
        return idx if idx >= 0 else 0
    except (TypeError, ValueError):
        return 0


def _matrix_entry_value(entry: Any) -> float:
    if not isinstance(entry, dict):
        return 0.0
    try:
        return float(entry.get("value", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def resolve_price_matrix_entry(
    field: Dict[str, Any],
    option_index: int = 0,
    response_value: Any = None,
) -> Dict[str, Any]:
    price_matrix = field.get("priceMatrix") or {}
    if not isinstance(price_matrix, dict) or not price_matrix.get("enabled"):
        return {}

    entries = price_matrix.get("entries") or []
    if not entries:
        return {}

    options = field.get("options") or []

    if isinstance(response_value, dict):
        response_option_id = str(response_value.get("fieldOptionId") or "").strip().lower()
        if response_option_id:
            for entry in entries:
                if str((entry or {}).get("fieldOptionId") or "").strip().lower() == response_option_id:
                    return entry or {}

    if isinstance(response_value, str):
        response_text = response_value.strip().lower()
        if response_text:
            for idx, option in enumerate(options):
                option_label_text = str(option.get("label") or option.get("value") or option.get("name") or "").strip().lower()
                option_id_text = str(option.get("fieldOptionId") or "").strip().lower()
                if response_text == option_label_text or response_text == option_id_text:
                    option_id = str(option.get("fieldOptionId") or "").strip().lower()
                    if option_id:
                        for entry in entries:
                            if str((entry or {}).get("fieldOptionId") or "").strip().lower() == option_id:
                                return entry or {}
                    if idx < len(entries):
                        return entries[idx] or {}
                    break

    if options and 0 <= option_index < len(options):
        option = options[option_index] or {}
        option_id = str(option.get("fieldOptionId") or "").strip().lower()
        if option_id:
            for entry in entries:
                if str((entry or {}).get("fieldOptionId") or "").strip().lower() == option_id:
                    return entry or {}

    idx = option_index if option_index < len(entries) else 0
    entry = entries[idx] or {}
    return entry if isinstance(entry, dict) else {}


def extract_price_from_matrix(field: Dict[str, Any], option_index: int = 0, response_value: Any = None) -> float:
    entry = resolve_price_matrix_entry(field, option_index=option_index, response_value=response_value)
    return _matrix_entry_value(entry)


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


def extract_quantity_for_priced_field(field: Dict[str, Any], response_value: Any = None) -> float:
    field_type = str(field.get("type") or "").lower()
    unit_type = str(field.get("unitType") or "").lower()

    if field_type in {"number", "dimension"} or unit_type in {"number", "dimension", "quantity"}:
        quantity = infer_quantity_from_field(field, response_value, default=1.0)
        return quantity if quantity > 0 else 1.0

    return 1.0


def is_quantity_pricing_field(field: Dict[str, Any]) -> bool:
    field_type = str(field.get("type") or "").lower()
    unit_type = str(field.get("unitType") or "").lower()
    label = field_display_name(field).lower()
    description = str(field.get("description") or "").lower()
    blob = f"{label} {description}"

    if field_type == "dimension" or unit_type in {"dimension", "quantity"}:
        return True

    quantity_terms = [
        "sq ft",
        "sqft",
        "square feet",
        "square foot",
        "square meter",
        "square metre",
        "sqm",
        "sq m",
        "m2",
    ]
    return any(term in blob for term in quantity_terms)


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


def selected_option_indices(field: Dict[str, Any], response_value: Any) -> List[int]:
    field_type = str(field.get("type", "")).lower()
    options = field.get("options") or []

    if not options:
        return []

    if isinstance(response_value, dict):
        if "optionIndex" in response_value:
            return [normalize_option_index(response_value.get("optionIndex"))]
        if "fieldOptionId" in response_value:
            target = str(response_value.get("fieldOptionId")).strip().lower()
            for idx, option in enumerate(options):
                if str(option.get("fieldOptionId") or "").strip().lower() == target:
                    return [idx]

    if isinstance(response_value, list):
        indices: List[int] = []
        option_lookup = {
            str(opt.get("label", "")).strip().lower(): i
            for i, opt in enumerate(options)
        }
        option_id_lookup = {
            str(opt.get("fieldOptionId", "")).strip().lower(): i
            for i, opt in enumerate(options)
        }
        for value in response_value:
            if isinstance(value, (int, float)):
                indices.append(normalize_option_index(value))
                continue
            lowered = str(value).strip().lower()
            if lowered in option_lookup:
                indices.append(option_lookup[lowered])
            elif lowered in option_id_lookup:
                indices.append(option_id_lookup[lowered])
        return indices

    if isinstance(response_value, (int, float)) and field_type in {"dropdown", "radio", "yesno"}:
        return [normalize_option_index(response_value)]

    if isinstance(response_value, str):
        lowered = response_value.strip().lower()
        for idx, option in enumerate(options):
            if lowered == str(option.get("label", "")).strip().lower():
                return [idx]
            if lowered == str(option.get("fieldOptionId", "")).strip().lower():
                return [idx]

    return []


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
        unit_type = str(field.get("unitType") or "").lower()
        options = field.get("options") or []
        response_value = lookup_response_value(form_data, field.get("fieldName", ""))
        selected_indices = selected_option_indices(field, response_value)
        has_answer = response_value not in (None, "", [], {})
        if not has_answer:
            continue

        answer_text = answer_text_for_field(field, response_value, selected_indices)
        field_label = field_display_name(field)
        is_quantity_pricing = is_quantity_pricing_field(field)

        def should_skip_metadata_row() -> bool:
            if not answer_text:
                return True
            if is_quantity_pricing:
                return False
            if not is_generic_field_label(field_label):
                return False

            normalized = answer_text.strip().lower()
            service_like_terms = [
                "design",
                "package",
                "interior",
                "architecture",
                "room",
                "space",
                "plan",
                "style",
                "concept",
                "layout",
            ]
            if any(term in normalized for term in service_like_terms):
                return False

            numeric_like = bool(re.search(r"\d", normalized)) or any(token in normalized for token in ["$", "₹", "sqft", "sqm", "sq ft", "sq. ft", "month", "months", "year", "years", "budget", "area", "size"])
            return numeric_like

        if should_skip_metadata_row():
            continue

        if not options and not is_quantity_pricing:
            continue

        if field_type in {"multiselect", "checkbox"}:
            if not selected_indices:
                continue
            for option_index in selected_indices:
                unit_price = extract_price_from_matrix(field, option_index, response_value)
                if unit_price <= 0:
                    continue
                option_name = option_label(field, option_index) or answer_text
                item_name = option_name.strip() or field_label
                subtotal = float(unit_price)
                summary = (
                    f"Configured pricing rule 'selected_option' applied to {item_name}; "
                    f"unit price {unit_price:.2f}, quantity 1, subtotal {subtotal:.2f}."
                )
                items.append(
                    {
                        "itemName": item_name,
                        "selectedAnswer": option_name.strip() or answer_text,
                        "category": service_name,
                        "unitPrice": float(unit_price),
                        "quantity": 1.0,
                        "subtotal": float(subtotal),
                        "pricingRule": "selected_option",
                        "summary": summary,
                        "justification": f"Selected option: {item_name} under {field.get('fieldName', 'selected field')}",
                    }
                )
        else:
            selected_index = selected_indices[0] if selected_indices else 0
            unit_price = extract_price_from_matrix(field, selected_index, response_value)
            if unit_price <= 0:
                continue
            if is_quantity_pricing:
                quantity = extract_quantity_for_priced_field(field, response_value)
                subtotal = float(unit_price * quantity)
                selected_name = field_label
                selected_answer = answer_text or str(response_value).strip() or selected_name
                summary = (
                    f"Configured pricing rule 'per_unit' applied to {selected_name}; "
                    f"unit price {unit_price:.2f}, quantity {quantity:.2f}, subtotal {subtotal:.2f}."
                )
                items.append(
                    {
                        "itemName": selected_name,
                        "selectedAnswer": selected_answer,
                        "category": service_name,
                        "unitPrice": float(unit_price),
                        "quantity": float(quantity),
                        "subtotal": float(subtotal),
                        "pricingRule": "per_unit",
                        "summary": summary,
                        "justification": f"Per-unit pricing: {selected_name} at {unit_price:.2f} x {quantity:.2f}",
                    }
                )
                continue

            selected_name = option_label(field, selected_index) or answer_text or field_label
            subtotal = float(unit_price)
            summary = (
                f"Configured pricing rule 'selected_option' applied to {selected_name}; "
                f"unit price {unit_price:.2f}, quantity 1, subtotal {subtotal:.2f}."
            )
            items.append(
                {
                    "itemName": selected_name,
                    "selectedAnswer": answer_text or selected_name,
                    "category": service_name,
                    "unitPrice": float(unit_price),
                    "quantity": 1.0,
                    "subtotal": float(subtotal),
                    "pricingRule": "selected_option",
                    "summary": summary,
                    "justification": f"Selected option: {selected_name} under {field.get('fieldName', 'selected field')}",
                }
            )
    return items


def extract_user_selections(form_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extract a human-readable summary of the user's actual answers."""
    selections: List[Dict[str, str]] = []
    seen: set = set()

    for priced in collect_priced_fields(form_data):
        service_name = priced["serviceName"]
        field = priced["field"]
        field_name = str(field.get("fieldName") or "").strip()
        response_value = lookup_response_value(form_data, field_name)
        if response_value in (None, "", [], {}):
            continue

        selected_indices = selected_option_indices(field, response_value)
        answer_text = answer_text_for_field(field, response_value, selected_indices)
        if not answer_text:
            answer_text = str(response_value).strip()
        if not answer_text:
            continue

        question = str(field.get("description") or field_name or "Field").strip() or "Field"
        key = (service_name, question, answer_text)
        if key in seen:
            continue
        seen.add(key)
        selections.append(
            {
                "service": service_name,
                "question": question,
                "answer": answer_text,
            }
        )

    return selections


def build_pricing_table(form_data: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    items = extract_items(form_data)
    items = items[:8]
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
            {"value": "Subtotal", "label": "Subtotal"},
        ],
        "content": content,
        "calculationContent": content,
        "items": items,
        "lineItemSummaries": [
            {
                "itemName": item["itemName"],
                "selectedAnswer": item.get("selectedAnswer") or item["itemName"],
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
    "pricing_table_rows",
]


def fallback_pricing_ai_content(form_data: Dict[str, Any], pricing_table: Dict[str, Any], currency_code: str) -> Dict[str, Any]:
    city = (form_data.get("meta") or {}).get("city") or "your project location"
    subtotal = money(pricing_table["summary"]["subtotal"], currency_code)
    contingency = money(pricing_table["summary"]["contingency"], currency_code)
    total = money(pricing_table["summary"]["total"], currency_code)
    line_items = pricing_table.get("lineItemSummaries") or []
    scope_summary = ", ".join(
        str(item.get("itemName", "")).split(": ", 1)[-1]
        for item in line_items[:3]
        if str(item.get("itemName", "")).strip()
    )
    if not scope_summary:
        scope_summary = "the selected project scope"
    return {
        "pricing_intro": f"The pricing below has been tailored for {city} and reflects {scope_summary} together with the complexity, sequencing, and delivery effort implied by the submitted answers.",
        "pricing_summary_note": f"Subtotal {subtotal}, contingency reserve {contingency}, and total {total} are derived from the submitted answers and pricing rules.",
        "justification_title": "Investment Breakdown & Value Framework",
        "justification_sections": [
            f"The subtotal of {subtotal} reflects the selected answers, the defined scope, and the effort needed to deliver the work for {city}.",
            f"A contingency reserve of {contingency} protects against changes in scope, coordination, and site conditions.",
            f"The total investment of {total} includes the subtotal plus contingency, keeping the proposal financially clear and traceable.",
        ],
        "line_item_notes": [
            f"{item['itemName']}: {item['summary']}" for item in line_items
        ] or [
            "Line-item pricing follows the configured pricing rules in the submitted form.",
        ],
        "pricing_table_rows": fallback_pricing_table_rows(form_data, pricing_table, currency_code),
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
        elif key == "pricing_table_rows":
            rows = normalize_pricing_table_rows(value)
            normalized[key] = rows or fallback[key]
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
    table_row_blob = " ".join(" ".join(row) for row in (normalized.get("pricing_table_rows") or [])).lower()

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
    if pricing_table.get("lineItemSummaries") and len(normalized.get("pricing_table_rows") or []) < 1:
        issues.append("Pricing content should include AI-generated pricing table rows.")
    if "site assessment" not in table_row_blob and "concept design" not in table_row_blob and pricing_table.get("lineItemSummaries"):
        issues.append("Pricing table rows should resemble proposal phase breakdown rows.")

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
        "projectQuantity": infer_pricing_quantity(form_data),
        "projectContext": project_context_for_pricing(form_data),
        "projectType": lookup_response_value(form_data, "Project Type") or lookup_response_value(form_data, "projectType") or "",
        "selectedServices": [s.get("serviceName") for s in parse_services(form_data)],
        "userSelections": extract_user_selections(form_data),
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
pricing_intro, pricing_summary_note, justification_title, justification_sections, line_item_notes, pricing_table_rows

This content is for the pricing page and pricing justification only.
It must explain the pricing summary using the provided subtotal, contingency, and total.
Do not change any numeric amounts.
Do not invent extra services or line items beyond the provided pricingItems.
Do not write generic marketing copy. Make it specific, grounded, and proposal-ready.
Each justification section should be 1-3 sentences long.
Each line item note should be 1 sentence and should explain the configured pricing rule or business reason.
pricing_table_rows must be an array of 8 rows shaped like [name, price, quantity].
The rows should look like a proposal phase breakdown driven by the submitted answers.
Do not return generic labels like "Service 1" or "Phase 1".
Use the user's project type, city, selected services, selected room/area, and quantity to personalize the row names.
Use the project's actual area or quantity in the Quantity column when available.
Keep the Price column as a phase multiplier or factor such as 1, 3, 1.5, 2.50.
For example, if the project is commercial, use commercial design phases. If the user selected Bedroom, Kitchen, or Living Room, make the row names specific to that selected space.

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
    subtotal = money(pricing_table["summary"]["subtotal"], currency_code)
    items = extract_items(form_data)
    selections = extract_user_selections(form_data)
    item_names = [item["itemName"] for item in items[:3] if str(item.get("itemName", "")).strip()]
    services_text = ", ".join(item_names) if item_names else "the selected architectural services"
    answer_snapshot = ", ".join(
        selection["answer"]
        for selection in selections[:3]
        if str(selection.get("answer", "")).strip()
    ) or services_text
    return {
        "title": "Interior Design & Architecture Proposal",
        "subtitle": f"Tailored design solutions for your {city} project",
        "pricing_intro": (
            f"The following investment structure covers {answer_snapshot} "
            f"for your project in {city}."
        ),
        "justification_title": "Investment Breakdown & Value Framework",
        "justification_sections": [
            (
                f"Your investment of {subtotal} covers {services_text}. "
                f"Each service includes professional design expertise, project coordination, and quality delivery."
            ),
            (
                f"The pricing for your {city} project accounts for local market conditions, material costs, "
                f"and the specific scope of work you selected."
            ),
            (
                f"A 10% contingency reserve of {contingency} is included as an industry-standard safeguard, "
                f"bringing your total investment to {total}."
            ),
        ],
        "acceptance_intro": (
            f"We are excited to bring your interior design vision to life. "
            f"By signing below, you authorize us to begin work on your {city} project under the terms outlined in this proposal."
        ),
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

    user_selections = extract_user_selections(form_data)
    items = extract_items(form_data)

    prompt_payload = {
        "currency": currency_code,
        "city": (form_data.get("meta") or {}).get("city", ""),
        "services": [s.get("serviceName") for s in parse_services(form_data)],
        "userSelections": user_selections,
        "lineItems": [
            {"name": item["itemName"], "price": money(item["unitPrice"], currency_code)}
            for item in items
        ],
        "pricingSummary": pricing_table["summary"],
    }

    prompt = f"""
You are writing a professional proposal for an architecture/interior design project.
The client filled out a lead capture form. Use their ACTUAL answers to write
specific, personalized content - not generic text.

Client's answers:
{json.dumps(user_selections, ensure_ascii=False, indent=2)}

Selected services and pricing:
{json.dumps([{"name": item["itemName"], "price": money(item["unitPrice"], currency_code)} for item in items], ensure_ascii=False, indent=2)}

Project total: {money(pricing_table["summary"]["total"], currency_code)}
Location: {(form_data.get("meta") or {}).get("city", "not specified")}

Return ONLY valid JSON with these exact keys:
{{
  "title": "specific project title based on what they selected",
  "subtitle": "specific subtitle mentioning their choices",
  "pricing_intro": "2 sentences explaining this specific client's investment",
  "justification_title": "title for the justification section",
  "justification_sections": [
    "paragraph 1: explain what they selected and why it costs what it does",
    "paragraph 2: explain the value and expertise included",
    "paragraph 3: explain contingency and total investment"
  ],
  "acceptance_intro": "warm closing specific to their project"
}}

justification_sections MUST be a JSON array of 3 plain text strings.
Do NOT return objects or dicts inside the array.
Reference the client's actual selections and amounts in your writing.
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
    pricing_table = apply_ai_pricing_table_rows(pricing_table, pricing_judge_report.get("corrected_content") or pricing_ai_content, form_data, currency_code)
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


def build_proposal_stream_iterator(form_data: Dict[str, Any], currency_code: str):
    def sse(event: str, data: Any) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=True)}\n\n"

    def iterator():
        yield sse("start", {"status": "started", "currency": currency_code})

        yield sse("stage", {"name": "pricing", "status": "running"})
        pricing_table = build_pricing_table(form_data, currency_code)
        yield sse(
            "pricing_table",
            {
                "content": pricing_table.get("content", []),
                "header": pricing_table.get("header", []),
                "items": pricing_table.get("items", []),
                "lineItemSummaries": pricing_table.get("lineItemSummaries", []),
                "summary": pricing_table.get("summary", {}),
                "justifications": pricing_table.get("justifications", {}),
            },
        )
        yield sse("stage", {"name": "pricing", "status": "done", "summary": pricing_table.get("summary", {})})

        yield sse("stage", {"name": "pricing_ai", "status": "running"})
        pricing_ai_content = call_digitalocean_pricing_ai(form_data, pricing_table, currency_code)
        yield sse("stage", {"name": "pricing_ai", "status": "done", "content": pricing_ai_content})

        yield sse("stage", {"name": "pricing_judge", "status": "running"})
        pricing_judge_report = call_digitalocean_pricing_judge(form_data, pricing_table, pricing_ai_content, currency_code)
        yield sse("stage", {"name": "pricing_judge", "status": "done", "validation": pricing_judge_report})

        pricing_table = apply_ai_pricing_table_rows(
            pricing_table,
            pricing_judge_report.get("corrected_content") or pricing_ai_content,
            form_data,
            currency_code,
        )
        yield sse(
            "pricing_table_rows",
            {
                "content": pricing_table.get("content", []),
                "header": pricing_table.get("header", []),
            },
        )

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
        yield sse("pages", result.get("pages", []))
        yield sse("macros", result.get("macros", []))
        yield sse("result", result)
        yield sse("done", {"status": "completed"})

    return iterator


def load_endpoints() -> None:
    endpoints_path = Path(__file__).parent / "proposal-via-leadcapture" / "endpoint.py"
    spec = importlib.util.spec_from_file_location("proposal_endpoint", endpoints_path)
    if not spec or not spec.loader:
        raise ImportError(f"Could not load endpoints from {endpoints_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.register_routes(app, parse_raw_request_body, normalize_payload, build_proposal_stream_iterator)


load_endpoints()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("API_PORT", "8000")), reload=False)
