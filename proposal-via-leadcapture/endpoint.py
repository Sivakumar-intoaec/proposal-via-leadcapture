import json
import traceback
from typing import Any, Dict

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse


def register_routes(app, parse_raw_request_body, normalize_payload, build_proposal_stream_iterator):
    @app.post("/api/v1/pricingtable-with-ai")
    async def generate_pricing_table(request: Request):
        try:
            payload = parse_raw_request_body(await request.body())
            form_data = normalize_payload(payload)
            currency_code = ((form_data.get("meta") or {}).get("currency") or "USD").upper()
            return StreamingResponse(
                build_proposal_stream_iterator(form_data, currency_code)(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_INPUT",
                    "message": "Request body must be valid JSON.",
                    "hint": "Send either a raw JSON array of response objects or a JSON object. Make sure there are no trailing commas, comments, or extra text around the payload.",
                    "details": str(exc),
                },
            )
        except Exception as exc:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Internal server error ({type(exc).__name__}): {str(exc)}")

    @app.post("/api/v1/pricingtable-with-ai/stream")
    async def generate_pricing_table_stream(request: Request):
        try:
            payload = parse_raw_request_body(await request.body())
            form_data = normalize_payload(payload)
            currency_code = ((form_data.get("meta") or {}).get("currency") or "USD").upper()
            return StreamingResponse(
                build_proposal_stream_iterator(form_data, currency_code)(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_INPUT",
                    "message": "Request body must be valid JSON.",
                    "hint": "Send either a raw JSON array of response objects or a JSON object. Make sure there are no trailing commas, comments, or extra text around the payload.",
                    "details": str(exc),
                },
            )
        except Exception as exc:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Internal server error ({type(exc).__name__}): {str(exc)}")
