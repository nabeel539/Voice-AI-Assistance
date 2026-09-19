"""
CIMET Reconnect — Domain Models

Core domain models for the voice agent system.
These are internal representations — NOT coupled to external dataset shapes.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Enums ────────────────────────────────────────────────────────────────────


class JourneyStep(str, Enum):
    """Steps in the Energy journey."""
    PROPERTY_DETAILS = "property_details"
    ENERGY_DETAILS = "energy_details"
    USAGE_DETAILS = "usage_details"
    CUSTOMER_DETAILS = "customer_details"
    COMPLETION = "completion"


# Ordered list of steps for determining next step
JOURNEY_STEP_ORDER = [
    JourneyStep.PROPERTY_DETAILS,
    JourneyStep.ENERGY_DETAILS,
    JourneyStep.USAGE_DETAILS,
    JourneyStep.CUSTOMER_DETAILS,
    JourneyStep.COMPLETION,
]


class ConsentStatus(str, Enum):
    """Customer consent status."""
    PENDING = "pending"
    CONSENTED = "consented"
    DECLINED = "declined"


class EscalationReason(str, Enum):
    """Reasons for escalating to a human."""
    NONE = "none"
    FRUSTRATION = "frustration"
    CONFUSION = "confusion"
    HUMAN_REQUEST = "human_request"
    PAYMENT = "payment"
    OFF_SCRIPT = "off_script"
    SENSITIVE = "sensitive"
    LOW_CONFIDENCE = "low_confidence"
    ADVICE_REQUEST = "advice_request"
    REPEATED_FAILURE = "repeated_failure"


class CallStatus(str, Enum):
    """Status of a call."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DECLINED = "declined"
    HANDOFF = "handoff"
    FAILED = "failed"
    ENDED = "ended"


class JourneySubmissionStatus(str, Enum):
    """Status of journey submission."""
    NOT_STARTED = "not_started"
    READY = "ready"
    SUBMITTED = "submitted"
    SUCCESS = "success"
    FAILED = "failed"


# ─── Domain Models ────────────────────────────────────────────────────────────


class Lead(BaseModel):
    """Internal representation of a lead.
    
    This is the normalized model — the DatasetAdapter converts
    external dataset records into this shape.
    """
    lead_id: str
    last_completed_step: JourneyStep
    test_contact: str
    phone: Optional[str] = None
    customer_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def get_next_step(self) -> Optional[JourneyStep]:
        """Determine the next step after the last completed step."""
        try:
            current_index = JOURNEY_STEP_ORDER.index(self.last_completed_step)
            if current_index + 1 < len(JOURNEY_STEP_ORDER):
                return JOURNEY_STEP_ORDER[current_index + 1]
            return None  # Already completed all steps
        except ValueError:
            return JOURNEY_STEP_ORDER[0]  # Start from beginning if unknown


class FieldDefinition(BaseModel):
    """Definition of a field to collect during the journey."""
    name: str
    step: JourneyStep
    field_type: str = "string"
    required: bool = True
    question: str
    validation: Optional[dict[str, Any]] = None
    max_retries: int = 2
    escalation_condition: Optional[str] = None


class CollectedField(BaseModel):
    """A field value that has been collected and validated."""
    field_name: str
    value: Any
    confidence: float = 1.0
    validated: bool = False
    collected_at: datetime = Field(default_factory=datetime.utcnow)


class ConversationMessage(BaseModel):
    """A single message in the conversation."""
    role: str  # "agent" or "customer"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    audio_file: Optional[str] = None


class HandoffContext(BaseModel):
    """Context passed to a human agent during handoff."""
    lead_id: str
    current_step: JourneyStep
    reason: EscalationReason
    summary: str
    collected_fields: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    customer_statement: Optional[str] = None
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DNCResult(BaseModel):
    """Result of a Do-Not-Call check."""
    phone_number: str
    allowed: bool
    reason: Optional[str] = None


class ExtractionResult(BaseModel):
    """Result of extracting a field value from customer speech."""
    field: str
    value: Any
    confidence: float
    raw_text: str = ""


class JourneyPayload(BaseModel):
    """Payload to submit to the journey sandbox."""
    lead_id: str
    fields: dict[str, Any]
    completed_steps: list[str]
    submission_time: datetime = Field(default_factory=datetime.utcnow)
