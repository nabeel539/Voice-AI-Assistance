"""
CIMET Reconnect — Call State

Explicit state model for tracking call progress and journey state.
Uses deterministic state transitions — does NOT rely only on conversation history.
"""

from datetime import datetime
from typing import Any, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field

from app.domain.models import (
    CallStatus,
    CollectedField,
    ConsentStatus,
    ConversationMessage,
    EscalationReason,
    JourneyStep,
    JourneySubmissionStatus,
    JOURNEY_STEP_ORDER,
    Lead,
)


def _default_max_retries() -> int:
    try:
        from app.config import get_settings
        return get_settings().max_validation_retries
    except Exception:
        return 2


class CallState(BaseModel):
    """Complete state of an active call.
    
    This is the single source of truth for what's happening during a call.
    It tracks deterministic state so the agent knows what to do next
    without relying solely on conversation history / LLM memory.
    """

    call_id: str = Field(default_factory=lambda: str(uuid4()))
    lead_id: str
    current_step: JourneyStep = JourneyStep.PROPERTY_DETAILS
    completed_steps: list[JourneyStep] = Field(default_factory=list)
    collected_fields: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)

    # --- Call Status ---
    call_status: CallStatus = CallStatus.PENDING
    consent_status: ConsentStatus = ConsentStatus.PENDING

    # --- AI State ---
    confidence: float = 1.0
    current_field: Optional[str] = None
    retry_count: int = 0
    max_retries: int = Field(default_factory=_default_max_retries)

    # --- Escalation ---
    escalation_status: Optional[EscalationReason] = EscalationReason.NONE
    escalation_reason: Optional[str] = None

    # --- Conversation ---
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    conversation_summary: str = ""

    # --- Journey Submission ---
    journey_submission_status: JourneySubmissionStatus = JourneySubmissionStatus.NOT_STARTED

    # --- Timestamps ---
    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    # --- DNC ---
    dnc_checked: bool = False
    dnc_allowed: bool = False

    # --- Telephony / Transport Metadata ---
    channel: str = "browser"  # "browser" | "twilio"
    twilio_call_sid: Optional[str] = None
    twilio_stream_sid: Optional[str] = None
    to_phone: Optional[str] = None
    phone: Optional[str] = None

    # --- Reference Data (Unconfirmed Lead Metadata) ---
    reference_data: dict[str, Any] = Field(default_factory=dict)

    # --- Customer Identity & Review Confirmation ---
    customer_name_confirmed: bool = False
    confirmed_customer_name: Optional[str] = None
    in_final_review: bool = False
    final_confirmation_granted: bool = False

    # ─── State Transition Methods ─────────────────────────────────────────

    def mark_consent(self, status: ConsentStatus) -> "CallState":
        """Update consent status."""
        self.consent_status = status
        if status == ConsentStatus.DECLINED:
            self.call_status = CallStatus.DECLINED
        elif status == ConsentStatus.CONSENTED:
            self.call_status = CallStatus.IN_PROGRESS
        self._touch()
        return self

    def mark_dnc_checked(self, allowed: bool) -> "CallState":
        """Record DNC check result."""
        self.dnc_checked = True
        self.dnc_allowed = allowed
        self._touch()
        return self

    def save_field(self, field_name: str, value: Any, confidence: float = 1.0) -> "CallState":
        """Save a validated field value."""
        self.collected_fields[field_name] = value
        if field_name in self.missing_fields:
            self.missing_fields.remove(field_name)
        self.confidence = confidence
        self.retry_count = 0  # Reset retries on success
        self._touch()
        return self

    def increment_retry(self) -> "CallState":
        """Increment retry counter for current field."""
        self.retry_count += 1
        self._touch()
        return self

    def has_exceeded_retries(self) -> bool:
        """Check if retry limit has been exceeded."""
        return self.retry_count >= self.max_retries

    def advance_step(self, next_step: JourneyStep) -> "CallState":
        """Mark current step as complete and move to next."""
        if self.current_step not in self.completed_steps:
            self.completed_steps.append(self.current_step)
        self.current_step = next_step
        self.retry_count = 0
        self.current_field = None
        self._touch()
        return self

    def set_current_field(self, field_name: str) -> "CallState":
        """Set the field currently being collected."""
        self.current_field = field_name
        self._touch()
        return self

    def escalate(self, reason: EscalationReason, detail: str = "") -> "CallState":
        """Trigger escalation to human."""
        self.escalation_status = reason
        self.escalation_reason = detail
        self.call_status = CallStatus.HANDOFF
        self._touch()
        return self

    def complete_journey(self) -> "CallState":
        """Mark the journey as ready for submission."""
        if self.current_step not in self.completed_steps:
            self.completed_steps.append(self.current_step)
        self.journey_submission_status = JourneySubmissionStatus.READY
        self._touch()
        return self

    def mark_submitted(self, success: bool) -> "CallState":
        """Record journey submission result."""
        self.journey_submission_status = (
            JourneySubmissionStatus.SUCCESS if success 
            else JourneySubmissionStatus.FAILED
        )
        if success:
            self.call_status = CallStatus.COMPLETED
        self._touch()
        return self

    def add_message(self, role: str, content: str) -> "CallState":
        """Add a message to conversation history."""
        self.conversation_history.append(
            ConversationMessage(role=role, content=content)
        )
        self._touch()
        return self

    def get_next_step(self) -> Optional[JourneyStep]:
        """Determine the next uncompleted step."""
        for step in JOURNEY_STEP_ORDER:
            if step not in self.completed_steps:
                return step
        return None

    def is_journey_complete(self) -> bool:
        """Check if all journey steps are complete."""
        required_steps = [s for s in JOURNEY_STEP_ORDER if s != JourneyStep.COMPLETION]
        return all(s in self.completed_steps for s in required_steps)

    def should_escalate(self) -> bool:
        """Check if the current state warrants escalation."""
        return self.escalation_status != EscalationReason.NONE

    def is_active(self) -> bool:
        """Check if the call is still active (not ended/declined/handoff)."""
        return self.call_status in (CallStatus.PENDING, CallStatus.IN_PROGRESS)

    def _touch(self) -> None:
        """Update the last_updated timestamp."""
        self.last_updated = datetime.utcnow()

    @classmethod
    def from_lead(cls, lead: Union[Lead, str], last_completed_step: Optional[JourneyStep] = None) -> "CallState":
        """Create a new CallState from a lead, resuming after the last completed step."""
        phone_num = None
        reference_data: dict[str, Any] = {}
        if isinstance(lead, Lead):
            lead_id = lead.lead_id
            last_step = lead.last_completed_step
            phone_num = lead.phone or lead.test_contact
            if lead.first_name:
                reference_data["first_name"] = lead.first_name
            elif lead.customer_name:
                reference_data["first_name"] = lead.customer_name.split()[0]
                reference_data["customer_name"] = lead.customer_name
            if lead.last_name:
                reference_data["last_name"] = lead.last_name
            if lead.email:
                reference_data["email"] = lead.email
            if lead.phone or lead.test_contact:
                reference_data["phone"] = lead.phone or lead.test_contact
        else:
            lead_id = lead
            last_step = last_completed_step or JourneyStep.PROPERTY_DETAILS

        # Determine completed steps based on last_step
        completed = []
        for step in JOURNEY_STEP_ORDER:
            completed.append(step)
            if step == last_step:
                break

        # Next step is the one after last_step
        next_step_idx = JOURNEY_STEP_ORDER.index(last_step) + 1 if last_step in JOURNEY_STEP_ORDER else 0
        current = (
            JOURNEY_STEP_ORDER[next_step_idx]
            if next_step_idx < len(JOURNEY_STEP_ORDER)
            else JourneyStep.COMPLETION
        )

        # Pre-populate data from steps completed before the customer dropped off
        initial_fields: dict[str, Any] = {}
        if JourneyStep.PROPERTY_DETAILS in completed:
            initial_fields.update({
                "address": "100 Innovation Way",
                "suburb": "Sydney",
                "postcode": "2000",
            })
        if JourneyStep.ENERGY_DETAILS in completed:
            initial_fields.update({
                "energy_type": "electricity",
                "electricity_meter_type": "single_rate",
                "has_solar": False,
            })
        if JourneyStep.USAGE_DETAILS in completed:
            initial_fields.update({
                "electricity_usage": 1200,
                "usage_period": "quarterly",
            })
        if JourneyStep.CUSTOMER_DETAILS in completed:
            initial_fields.update({
                "first_name": reference_data.get("first_name", "Alex"),
                "last_name": reference_data.get("last_name", "Taylor"),
                "email": reference_data.get("email", "alex.taylor@example.com"),
            })

        return cls(
            lead_id=lead_id,
            current_step=current,
            completed_steps=completed,
            collected_fields=initial_fields,
            to_phone=phone_num,
            phone=phone_num,
            reference_data=reference_data,
        )
