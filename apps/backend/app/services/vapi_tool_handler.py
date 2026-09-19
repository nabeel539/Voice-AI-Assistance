"""
CIMET Reconnect — Vapi Controlled Tool Execution Handler

Processes Vapi assistant tool calls with strict session validation, idempotency caching,
and delegation to existing backend services (toolbox, dataset_adapter, handoff_service).
"""

import logging
from typing import Any, Dict, Optional, Set
from collections import OrderedDict

from app.api.session_store import session_store
from app.domain.call_state import CallState
from app.domain.models import CallStatus, EscalationReason, JourneyStep
from app.services.telemetry_logger import telemetry_logger

logger = logging.getLogger("cimet.vapi.tools")


class VapiToolHandler:
    """
    Executes controlled backend tools requested by the Vapi Voice Assistant.
    Provides tool call idempotency to prevent duplicate operations on network retries.
    """

    def __init__(self, cache_size: int = 1000):
        # LRU cache for idempotent tool call results: tool_call_id -> result_dict
        self._idempotency_cache: OrderedDict[str, Any] = OrderedDict()
        self._cache_size = cache_size

    def _cache_result(self, tool_call_id: str, result: Any) -> None:
        if not tool_call_id:
            return
        if len(self._idempotency_cache) >= self._cache_size:
            self._idempotency_cache.popitem(last=False)
        self._idempotency_cache[tool_call_id] = result

    def _get_cached_result(self, tool_call_id: str) -> Optional[Any]:
        if not tool_call_id:
            return None
        return self._idempotency_cache.get(tool_call_id)

    def execute_tool(
        self,
        tool_call_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        call_id_context: Optional[str] = None,
    ) -> Any:
        """
        Dispatch tool call with idempotency check, session validation, and strict error boundaries.
        """
        # 1. Check Idempotency Cache
        cached = self._get_cached_result(tool_call_id)
        if cached is not None:
            logger.info(f"[VAPI_TOOL_IDEMPOTENT] Replaying cached result for tool {tool_name} (ID: {tool_call_id})")
            return cached

        # 2. Resolve and Validate Call State
        resolved_call_id = parameters.get("call_id") or call_id_context
        call_state: Optional[CallState] = None
        if resolved_call_id:
            call_state = session_store.get_call(resolved_call_id)

        logger.info(f"[VAPI_TOOL_EXEC] Tool: {tool_name}, CallId: {resolved_call_id}, Params: {parameters}")

        # 3. Route to specific tool executor
        try:
            if tool_name == "get_lead":
                result = self._exec_get_lead(parameters, call_state)
            elif tool_name == "check_dnc":
                result = self._exec_check_dnc(parameters, call_state)
            elif tool_name == "get_current_journey_state":
                result = self._exec_get_current_journey_state(parameters, call_state)
            elif tool_name == "get_next_required_step":
                result = self._exec_get_next_required_step(parameters, call_state)
            elif tool_name == "validate_field":
                result = self._exec_validate_field(parameters, call_state)
            elif tool_name == "save_field":
                result = self._exec_save_field(parameters, call_state)
            elif tool_name == "submit_journey":
                result = self._exec_submit_journey(parameters, call_state)
            elif tool_name == "request_human_handoff":
                result = self._exec_request_human_handoff(parameters, call_state)
            elif tool_name == "end_call":
                result = self._exec_end_call(parameters, call_state)
            else:
                logger.warning(f"[VAPI_TOOL_UNKNOWN] Unsupported tool requested: {tool_name}")
                result = {
                    "success": False,
                    "error": f"Unknown tool: {tool_name}. Supported tools: get_lead, check_dnc, get_current_journey_state, get_next_required_step, validate_field, save_field, submit_journey, request_human_handoff, end_call",
                }
        except Exception as e:
            logger.error(f"[VAPI_TOOL_ERROR] Exception in tool {tool_name}: {e}", exc_info=True)
            result = {
                "success": False,
                "error": f"Internal tool execution error: {str(e)}",
            }

        # 4. Cache and Return Result
        self._cache_result(tool_call_id, result)
        return result

    # ── Tool Implementations ──────────────────────────────────────────────────

    def _exec_get_lead(self, params: Dict[str, Any], call_state: Optional[CallState]) -> Dict[str, Any]:
        lead_id = params.get("lead_id") or (call_state.lead_id if call_state else None)
        if not lead_id:
            return {"success": False, "error": "Missing lead_id parameter"}
        lead = session_store.dataset_adapter.get_lead(lead_id)
        if not lead:
            return {"success": False, "error": f"Lead {lead_id} not found"}
        return {
            "success": True,
            "lead_id": lead.lead_id,
            "customer_name": f"{lead.first_name or ''} {lead.last_name or ''}".strip() or getattr(lead, "customer_name", "Customer"),
            "postcode": getattr(lead, "postcode", ""),
            "last_completed_step": lead.last_completed_step.value if hasattr(lead.last_completed_step, "value") else str(lead.last_completed_step),
            "energy_type": getattr(lead, "energy_type", "electricity"),
            "channel": getattr(lead, "channel", "voice"),
        }

    def _exec_check_dnc(self, params: Dict[str, Any], call_state: Optional[CallState]) -> Dict[str, Any]:
        phone = params.get("phone_number") or (call_state.phone if call_state else None)
        if not phone:
            return {"success": False, "error": "Missing phone_number parameter"}
        dnc_result = session_store.toolbox.check_dnc(phone)
        if call_state:
            call_state.mark_dnc_checked(allowed=dnc_result.allowed)
        return {
            "success": True,
            "phone_number": phone,
            "allowed": dnc_result.allowed,
            "status": dnc_result.status,
            "reason": dnc_result.reason,
        }

    def _exec_get_current_journey_state(self, params: Dict[str, Any], call_state: Optional[CallState]) -> Dict[str, Any]:
        if not call_state:
            return {"success": False, "error": "CallState session not found for this call"}
        last_step = call_state.completed_steps[-1] if call_state.completed_steps else call_state.current_step
        missing_defs = session_store.toolbox.script_engine.get_missing_fields(call_state.current_step, call_state.collected_fields)
        missing_names = [f.name for f in missing_defs]
        return {
            "success": True,
            "call_id": call_state.call_id,
            "lead_id": call_state.lead_id,
            "last_completed_step": last_step.value if hasattr(last_step, "value") else str(last_step),
            "current_step": call_state.current_step.value if hasattr(call_state.current_step, "value") else str(call_state.current_step),
            "collected_fields": call_state.collected_fields,
            "missing_fields": missing_names,
            "consent_status": call_state.consent_status.value if hasattr(call_state.consent_status, "value") else str(call_state.consent_status),
            "escalation_status": call_state.escalation_status.value if hasattr(call_state.escalation_status, "value") else str(call_state.escalation_status),
        }

    def _exec_get_next_required_step(self, params: Dict[str, Any], call_state: Optional[CallState]) -> Dict[str, Any]:
        if not call_state:
            return {"success": False, "error": "CallState session not found for this call"}
        next_field_def = session_store.toolbox.script_engine.get_next_field(call_state.current_step, call_state.collected_fields)
        if not next_field_def:
            return {
                "success": True,
                "has_missing_fields": False,
                "message": "All required fields for this step have been collected. You may present the summary and proceed.",
            }
        return {
            "success": True,
            "has_missing_fields": True,
            "next_field": next_field_def.name,
            "question": next_field_def.question,
            "guidance": next_field_def.question or f"Collect {next_field_def.name}",
        }

    def _exec_validate_field(self, params: Dict[str, Any], call_state: Optional[CallState]) -> Dict[str, Any]:
        field_name = params.get("field_name")
        value = params.get("value")
        if not field_name or value is None:
            return {"success": False, "error": "Missing field_name or value parameter"}
        is_valid, err = session_store.toolbox.script_engine.validate_field(field_name, value)
        return {
            "success": True,
            "field_name": field_name,
            "valid": is_valid,
            "value": value,
            "error_message": err,
        }

    def _exec_save_field(self, params: Dict[str, Any], call_state: Optional[CallState]) -> Dict[str, Any]:
        if not call_state:
            return {"success": False, "error": "CallState session not found for this call"}
        field_name = params.get("field_name")
        value = params.get("value")
        if not field_name or value is None:
            return {"success": False, "error": "Missing field_name or value parameter"}

        # Validate against ScriptEngine definitions
        is_valid, err = session_store.toolbox.script_engine.validate_field(field_name, value)
        if not is_valid:
            return {
                "success": False,
                "field_name": field_name,
                "valid": False,
                "error": err or "Field value validation failed",
            }

        # Persist confirmed field
        call_state.collected_fields[field_name] = value
        if session_store.toolbox.script_engine.is_step_complete(call_state.current_step, call_state.collected_fields):
            if call_state.current_step not in call_state.completed_steps:
                call_state.completed_steps.append(call_state.current_step)
        session_store.save_call(call_state)

        telemetry_logger.log(
            "FIELD_COLLECTED",
            f"Confirmed field '{field_name}' = '{value}'",
            level="SUCCESS",
            category="journey",
            call_id=call_state.call_id,
            field_name=field_name,
        )

        missing_defs = session_store.toolbox.script_engine.get_missing_fields(call_state.current_step, call_state.collected_fields)
        return {
            "success": True,
            "field_name": field_name,
            "saved_value": value,
            "remaining_missing": [f.name for f in missing_defs],
        }

    def _exec_submit_journey(self, params: Dict[str, Any], call_state: Optional[CallState]) -> Dict[str, Any]:
        if not call_state:
            return {"success": False, "error": "CallState session not found for this call"}

        # Execute submission via toolbox
        submission = session_store.toolbox.submit_journey(
            lead_id=call_state.lead_id,
            collected_fields=call_state.collected_fields,
        )
        if submission.success:
            call_state.mark_journey_completed(
                submission_id=submission.submission_id or f"SUB-{call_state.lead_id}"
            )
            session_store.save_call(call_state)
            telemetry_logger.log(
                "JOURNEY_SUBMITTED",
                f"Journey submitted successfully (Submission ID: {submission.submission_id})",
                level="SUCCESS",
                category="journey",
                call_id=call_state.call_id,
                submission_id=submission.submission_id,
            )
            return {
                "success": True,
                "submission_id": submission.submission_id,
                "message": "Journey successfully recovered and submitted to CIMET CRM.",
            }
        else:
            return {
                "success": False,
                "error": submission.error_message or "Failed submitting journey to CIMET CRM",
            }

    def _exec_request_human_handoff(self, params: Dict[str, Any], call_state: Optional[CallState]) -> Dict[str, Any]:
        if not call_state:
            return {"success": False, "error": "CallState session not found for this call"}
        reason_str = params.get("reason", "customer_requested")
        summary = params.get("summary", "Human operator requested by customer or agent.")

        # Map to enum
        reason_map = {
            "customer_requested": EscalationReason.HUMAN_REQUEST,
            "human_request": EscalationReason.HUMAN_REQUEST,
            "frustrated": EscalationReason.FRUSTRATION,
            "frustration": EscalationReason.FRUSTRATION,
            "confusion": EscalationReason.CONFUSION,
            "payment": EscalationReason.PAYMENT,
            "off_script": EscalationReason.OFF_SCRIPT,
        }
        escalation_reason = reason_map.get(reason_str, EscalationReason.HUMAN_REQUEST)

        handoff_pkg = session_store.toolbox.create_handoff(
            call_state=call_state,
            reason=escalation_reason,
            customer_statement=summary,
            summary=summary,
        )
        call_state.escalate(reason=escalation_reason, detail=summary)
        session_store.save_call(call_state)
        session_store.save_call(call_state)

        telemetry_logger.log(
            "HUMAN_HANDOFF_TRIGGERED",
            f"Escalated to human operator: {summary} (Reason: {escalation_reason.value})",
            level="WARNING",
            category="handoff",
            call_id=call_state.call_id,
            escalation_reason=escalation_reason.value,
        )

        return {
            "success": True,
            "handoff_id": handoff_pkg.handoff_id,
            "action": "transfer",
            "destination": "+611300000000",
            "message": "Human handoff package prepared. Initiating operator transfer.",
        }

    def _exec_end_call(self, params: Dict[str, Any], call_state: Optional[CallState]) -> Dict[str, Any]:
        if call_state:
            call_state.call_status = CallStatus.ENDED
            session_store.save_call(call_state)
            telemetry_logger.log(
                "CALL_ENDED",
                f"Call finalized: {params.get('reason', 'normal_completion')}",
                level="INFO",
                category="telephony",
                call_id=call_state.call_id,
            )
        return {
            "success": True,
            "action": "hangup",
            "message": "Call cleanly concluded.",
        }


# Global instance
vapi_tool_handler = VapiToolHandler()
