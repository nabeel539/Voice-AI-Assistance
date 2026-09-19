"""
CIMET Reconnect — Vapi Server Webhook Router

Receives and processes Vapi cloud events:
- Authenticates webhook requests with X-Vapi-Secret
- Dispatches tool-calls to VapiToolHandler
- Synchronizes call status updates
- Captures transcripts for real-time console observability
- Finalizes end-of-call reports
"""

import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel

from app.api.session_store import session_store
from app.config import get_settings
from app.domain.models import CallStatus
from app.services.telemetry_logger import telemetry_logger
from app.services.vapi_tool_handler import vapi_tool_handler

logger = logging.getLogger("cimet.vapi.webhook")
router = APIRouter(prefix="/api/webhooks", tags=["vapi-webhook"])


@router.post("/vapi")
async def handle_vapi_webhook(
    request: Request,
    x_vapi_secret: Optional[str] = Header(None, alias="x-vapi-secret"),
):
    """
    Main Vapi Server URL Webhook.
    Handles tool-calls, status updates, live transcripts, and end-of-call summaries.
    """
    settings = get_settings()

    # 1. Webhook Secret Authentication
    if settings.vapi_webhook_secret:
        auth_header = x_vapi_secret or request.headers.get("x-vapi-secret") or request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            auth_header = auth_header[7:]
        if auth_header != settings.vapi_webhook_secret and settings.app_env == "production":
            logger.warning(f"[VAPI_AUTH_FAILED] Invalid webhook secret from {request.client.host if request.client else 'unknown'}")
            raise HTTPException(status_code=401, detail="Invalid Vapi webhook secret")

    # 2. Parse Event Payload
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"[VAPI_WEBHOOK_PARSE_ERROR] Failed parsing JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    message = body.get("message", {})
    event_type = message.get("type") or body.get("type", "unknown")
    call_data = message.get("call", {}) or body.get("call", {})
    vapi_call_id = call_data.get("id") or message.get("callId")

    # Resolve internal call_id from session variables or mapping
    variables = (
        call_data.get("assistantOverrides", {}).get("variableValues", {})
        or message.get("variableValues", {})
        or {}
    )
    call_id = variables.get("call_id")

    call_state = None
    if call_id:
        call_state = session_store.get_call(call_id)
    if not call_state and vapi_call_id:
        call_state = session_store.get_call_by_twilio_sid(vapi_call_id)  # Reuses provider ID mapping

    if call_state and vapi_call_id and not call_state.twilio_call_sid:
        call_state.twilio_call_sid = vapi_call_id
        session_store.map_twilio_call(vapi_call_id, call_state.call_id)

    logger.info(f"[VAPI_WEBHOOK_EVENT] Type: {event_type}, CallId: {call_id}, VapiCallId: {vapi_call_id}")

    # ── 3. Handle Tool Calls Event ────────────────────────────────────────────
    if event_type == "tool-calls":
        tool_calls = message.get("toolCalls", []) or message.get("toolCallList", [])
        results: List[Dict[str, Any]] = []

        for tc in tool_calls:
            tc_id = tc.get("id") or tc.get("toolCallId", "")
            func = tc.get("function", {})
            name = func.get("name") or tc.get("name", "")
            raw_args = func.get("arguments", {}) or tc.get("parameters", {})

            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}
            else:
                args = raw_args or {}

            # Execute tool with idempotency check
            result = vapi_tool_handler.execute_tool(
                tool_call_id=tc_id,
                tool_name=name,
                parameters=args,
                call_id_context=call_id,
            )

            results.append({
                "toolCallId": tc_id,
                "result": json.dumps(result) if isinstance(result, (dict, list)) else str(result),
            })

            telemetry_logger.log(
                "VAPI_TOOL_EXECUTED",
                f"Tool '{name}' executed -> {str(result)[:100]}",
                level="INFO",
                category="vapi",
                call_id=call_id,
                tool_name=name,
            )

        return {"results": results}

    # ── 4. Handle Status Updates ──────────────────────────────────────────────
    elif event_type == "status-update":
        status_str = message.get("status")
        logger.info(f"[VAPI_STATUS_UPDATE] Status: {status_str} for Call {call_id}")

        if call_state and status_str:
            if status_str in ("in-progress", "ringing"):
                call_state.call_status = CallStatus.IN_PROGRESS
            elif status_str in ("ended", "completed", "closed"):
                call_state.call_status = CallStatus.ENDED
            elif status_str == "failed":
                call_state.call_status = CallStatus.FAILED
            session_store.save_call(call_state)

            telemetry_logger.log(
                "VAPI_STATUS_UPDATE",
                f"Vapi Call status: {status_str.upper()}",
                level="INFO",
                category="vapi",
                call_id=call_id,
                status=status_str,
            )
        return {"status": "ok"}

    # ── 5. Handle Live Transcripts (Observability Only) ────────────────────────
    elif event_type == "transcript":
        transcript_type = message.get("transcriptType", "final")
        role = message.get("role", "customer")
        text = message.get("transcript", "")

        if text and transcript_type == "final" and call_state:
            mapped_role = "assistant" if role == "assistant" else "user"
            call_state.add_message(mapped_role, text)
            session_store.save_call(call_state)

            telemetry_logger.log(
                "TRANSCRIPT",
                f"{mapped_role.capitalize()}: \"{text}\"",
                level="SPEECH",
                category="vapi",
                call_id=call_id,
                role=mapped_role,
            )
        return {"status": "ok"}

    # ── 6. Handle End of Call Report ──────────────────────────────────────────
    elif event_type == "end-of-call-report":
        summary = message.get("summary", "")
        ended_reason = message.get("endedReason", "normal")
        logger.info(f"[VAPI_END_OF_CALL] Call {call_id} ended. Reason: {ended_reason}")

        if call_state:
            call_state.call_status = CallStatus.ENDED
            if summary:
                call_state.conversation_summary = summary
            session_store.save_call(call_state)

            telemetry_logger.log(
                "CALL_SUMMARY",
                f"Call concluded ({ended_reason}). Summary: {summary[:150]}",
                level="SUCCESS",
                category="vapi",
                call_id=call_id,
                ended_reason=ended_reason,
            )
        return {"status": "ok"}

    # ── 7. Default Acknowledgment for Other Events ───────────────────────────
    return {"status": "ok"}
