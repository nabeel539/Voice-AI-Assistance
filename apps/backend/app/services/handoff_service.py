"""
CIMET Reconnect — Human Handoff Service

Packages complete contextual handoff dossiers when an AI interaction must escalate to a human agent.
Ensures zero repeat information for the customer.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from app.domain.call_state import CallState
from app.domain.models import EscalationReason, JourneyStep, CallStatus
from app.services.guardrail_service import redact_payment_info


class HandoffPackage(BaseModel):
    """Structured context package handed off to the human agent console."""
    handoff_id: str = Field(default_factory=lambda: f"HND-{uuid4().hex[:8].upper()}")
    lead_id: str
    call_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    current_step: JourneyStep
    escalation_reason: EscalationReason
    customer_statement: str
    summary: str
    collected_fields: Dict[str, Any]
    missing_fields: List[str]
    suggested_operator_action: str


class HandoffService:
    """Manages escalation lifecycle and formats handoff packages."""

    def __init__(self):
        self._handoff_records: List[HandoffPackage] = []

    def create_handoff(
        self,
        call_state: CallState,
        reason: EscalationReason,
        customer_statement: str,
        summary: Optional[str] = None,
    ) -> HandoffPackage:
        """Construct a complete handoff package and transition call state."""
        # Sanitize customer statement to prevent card or sensitive leaks
        safe_customer_statement = redact_payment_info(customer_statement)

        # Suggest operator opening lines based on reason
        operator_actions = {
            EscalationReason.PAYMENT: "Customer mentioned payment/billing. Reassure security and handle payment via secure operator terminal.",
            EscalationReason.ADVICE_REQUEST: "Customer requested retailer comparison/advice. Review current market offers with them.",
            EscalationReason.HUMAN_REQUEST: "Customer requested human assistance. Warm transfer, continue from missing fields.",
            EscalationReason.FRUSTRATION: "Customer expressed frustration. Apologize for automated friction and offer direct human assistance.",
            EscalationReason.CONFUSION: "Customer was confused by automated journey questions. Clarify questions in plain English.",
            EscalationReason.SENSITIVE: "Customer situation involves vulnerability/bereavement/hardship. Handle with empathy and specialized policy.",
            EscalationReason.OFF_SCRIPT: "Customer asked off-topic questions. Help them determine if they wish to complete energy comparison.",
            EscalationReason.LOW_CONFIDENCE: "Voice quality or transcription ambiguity. Verify last collected field and resume.",
            EscalationReason.REPEATED_FAILURE: "Repeated validation failures on current field. Manually input value.",
        }

        action = operator_actions.get(reason, "Resume energy comparison journey from last collected step.")
        
        # Build concise conversation summary if not provided (safe from card data)
        if not summary:
            if reason == EscalationReason.PAYMENT:
                summary = "Customer raised a payment/card-related issue."
            else:
                collected_summary = ", ".join(f"{k}: {v}" for k, v in call_state.collected_fields.items()) or "None yet"
                summary = (
                    f"Customer lead {call_state.lead_id} escalated during step '{call_state.current_step.value}'. "
                    f"Escalation trigger: {reason.value}. "
                    f"Fields collected so far: {collected_summary}."
                )
        else:
            summary = redact_payment_info(summary)

        # Transition the call state
        call_state.escalate(reason=reason, detail=safe_customer_statement)

        # Resolve missing fields from state or calculate uncollected fields
        missing = list(call_state.missing_fields)
        if not missing:
            all_fields = [
                "address", "suburb", "postcode",
                "energy_type", "electricity_meter_type", "has_solar",
                "electricity_usage", "usage_period",
                "first_name", "last_name", "email"
            ]
            missing = [f for f in all_fields if f not in call_state.collected_fields]

        package = HandoffPackage(
            lead_id=call_state.lead_id,
            call_id=call_state.call_id,
            current_step=call_state.current_step,
            escalation_reason=reason,
            customer_statement=safe_customer_statement,
            summary=summary,
            collected_fields=dict(call_state.collected_fields),
            missing_fields=missing,
            suggested_operator_action=action,
        )

        self._handoff_records.append(package)
        return package



    def get_handoff(self, handoff_id: str) -> Optional[HandoffPackage]:
        """Retrieve a specific handoff package."""
        for record in self._handoff_records:
            if record.handoff_id == handoff_id:
                return record
        return None

    def get_all_handoffs(self) -> List[HandoffPackage]:
        """List all handoff records."""
        return list(self._handoff_records)
