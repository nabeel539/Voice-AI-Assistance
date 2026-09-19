"""
CIMET Reconnect — Journey Service & Payload Builder

Transforms internal domain state into external CIMET Energy journey payloads
and handles submission to the journey sandbox.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field

from app.domain.models import JourneySubmissionStatus


class CIMETEnergyPayload(BaseModel):
    """External payload structure required by CIMET Energy Journey API."""
    journey_reference: str = Field(default_factory=lambda: f"CIMET-REC-{uuid4().hex[:8].upper()}")
    lead_id: str
    property_details: Dict[str, Any]
    energy_details: Dict[str, Any]
    usage_details: Dict[str, Any]
    customer_details: Dict[str, Any]
    meta: Dict[str, Any] = Field(default_factory=lambda: {
        "channel": "ai_voice_recovery",
        "version": "1.0",
        "generated_at": datetime.utcnow().isoformat(),
    })


class PayloadValidationResult(BaseModel):
    """Result of validating a generated payload before submission."""
    valid: bool
    missing_fields: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class SubmissionResult(BaseModel):
    """Result of submitting a payload to the journey sandbox/API."""
    status: JourneySubmissionStatus
    reference_id: Optional[str] = None
    http_status_code: int = 200
    message: str = ""
    payload: Optional[Dict[str, Any]] = None
    submitted_at: datetime = Field(default_factory=datetime.utcnow)


class PayloadBuilder:
    """Decouples internal collected fields from external partner/sandbox payload format."""

    REQUIRED_FIELDS = [
        "address", "suburb", "postcode",
        "energy_type", "electricity_meter_type", "has_solar",
        "electricity_usage", "usage_period",
        "first_name", "last_name", "email"
    ]

    @classmethod
    def validate_fields(cls, collected_fields: Dict[str, Any]) -> PayloadValidationResult:
        """Verify that all required energy fields exist and are non-empty."""
        missing = []
        for f in cls.REQUIRED_FIELDS:
            val = collected_fields.get(f)
            if val is None or (isinstance(val, str) and not val.strip()):
                missing.append(f)

        if missing:
            return PayloadValidationResult(
                valid=False,
                missing_fields=missing,
                errors=[f"Missing required field for submission: {f}" for f in missing],
            )
        return PayloadValidationResult(valid=True)

    @classmethod
    def build(cls, lead_id: str, collected_fields: Dict[str, Any]) -> CIMETEnergyPayload:
        """Construct the external CIMET Energy payload schema."""
        return CIMETEnergyPayload(
            lead_id=lead_id,
            property_details={
                "address": collected_fields.get("address"),
                "suburb": collected_fields.get("suburb"),
                "postcode": collected_fields.get("postcode"),
            },
            energy_details={
                "energy_type": collected_fields.get("energy_type"),
                "electricity_meter_type": collected_fields.get("electricity_meter_type"),
                "has_solar": collected_fields.get("has_solar"),
            },
            usage_details={
                "electricity_usage": collected_fields.get("electricity_usage"),
                "usage_period": collected_fields.get("usage_period"),
            },
            customer_details={
                "first_name": collected_fields.get("first_name"),
                "last_name": collected_fields.get("last_name"),
                "email": collected_fields.get("email"),
            },
        )


class JourneyService(ABC):
    """Abstract interface for validating and submitting customer journey completions."""

    @abstractmethod
    def validate_payload(self, lead_id: str, collected_fields: Dict[str, Any]) -> PayloadValidationResult:
        """Validate if the collected fields are sufficient to build a compliant payload."""
        ...

    @abstractmethod
    def submit_journey(self, lead_id: str, collected_fields: Dict[str, Any]) -> SubmissionResult:
        """Submit the completed journey to the backend sandbox."""
        ...


class MockJourneyService(JourneyService):
    """Mock implementation of the Journey Sandbox for local testing and hackathon verification."""

    def __init__(self, simulate_failure: bool = False):
        self.simulate_failure = simulate_failure
        self.submissions: List[SubmissionResult] = []

    def validate_payload(self, lead_id: str, collected_fields: Dict[str, Any]) -> PayloadValidationResult:
        return PayloadBuilder.validate_fields(collected_fields)

    def submit_journey(self, lead_id: str, collected_fields: Dict[str, Any]) -> SubmissionResult:
        val = self.validate_payload(lead_id, collected_fields)
        if not val.valid:
            return SubmissionResult(
                status=JourneySubmissionStatus.FAILED,
                http_status_code=422,
                message=f"Validation failed: {', '.join(val.missing_fields)} missing",
            )

        if self.simulate_failure:
            return SubmissionResult(
                status=JourneySubmissionStatus.FAILED,
                http_status_code=500,
                message="Simulated downstream CIMET sandbox error (500 Internal Server Error)",
            )

        payload = PayloadBuilder.build(lead_id, collected_fields)
        result = SubmissionResult(
            status=JourneySubmissionStatus.SUBMITTED,
            reference_id=payload.journey_reference,
            http_status_code=200,
            message="Successfully recovered dropped energy comparison journey in CIMET sandbox.",
            payload=payload.model_dump(),
        )
        self.submissions.append(result)
        return result
