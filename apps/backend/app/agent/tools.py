"""
CIMET Reconnect — Agent Tools

Pure, testable tool functions wrapping domain services for use by the LangGraph agent.
"""

from typing import Any, Dict, Optional, Tuple

from app.domain.call_state import CallState
from app.domain.models import EscalationReason, JourneyStep
from app.services.consent_service import ConsentEvaluation, ConsentService
from app.services.dnc_service import DNCResult, DNCService, MockDNCService
from app.services.extraction_service import ExtractedField, ExtractionService
from app.services.guardrail_service import GuardrailCheckResult, GuardrailService
from app.services.handoff_service import HandoffPackage, HandoffService
from app.services.journey_service import JourneyService, MockJourneyService, SubmissionResult
from app.services.script_engine import ScriptEngine


class AgentToolbox:
    """Dependency container holding configured services for the agent workflow."""

    def __init__(
        self,
        script_engine: Optional[ScriptEngine] = None,
        dnc_service: Optional[DNCService] = None,
        consent_service: Optional[ConsentService] = None,
        guardrail_service: Optional[GuardrailService] = None,
        extraction_service: Optional[ExtractionService] = None,
        handoff_service: Optional[HandoffService] = None,
        journey_service: Optional[JourneyService] = None,
    ):
        self.script_engine = script_engine or ScriptEngine()
        self.dnc_service = dnc_service or MockDNCService()
        self.consent_service = consent_service or ConsentService()
        self.guardrail_service = guardrail_service or GuardrailService()
        self.extraction_service = extraction_service or ExtractionService(self.script_engine)
        self.handoff_service = handoff_service or HandoffService()
        self.journey_service = journey_service or MockJourneyService()

    def check_dnc(self, phone_number: str) -> DNCResult:
        """Verify phone number against Do-Not-Call list."""
        return self.dnc_service.check(phone_number)

    def evaluate_consent(self, utterance: str) -> ConsentEvaluation:
        """Evaluate customer's response to the recording consent request."""
        return self.consent_service.evaluate(utterance)

    def check_guardrails(self, utterance: str, confidence: float = 1.0) -> GuardrailCheckResult:
        """Run all 11 deterministic safety boundaries."""
        return self.guardrail_service.check(utterance, confidence=confidence)

    def extract_and_validate_field(
        self,
        field_name: str,
        utterance: str,
        reference_value: Optional[Any] = None,
    ) -> ExtractedField:
        """Extract and deterministically validate a target field."""
        return self.extraction_service.extract_field(field_name, utterance, reference_value=reference_value)

    def create_handoff(
        self,
        call_state: CallState,
        reason: EscalationReason,
        customer_statement: str,
        summary: Optional[str] = None,
    ) -> HandoffPackage:
        """Create a complete contextual handoff package for human transfer."""
        return self.handoff_service.create_handoff(
            call_state=call_state,
            reason=reason,
            customer_statement=customer_statement,
            summary=summary,
        )

    def submit_journey(self, lead_id: str, collected_fields: Dict[str, Any]) -> SubmissionResult:
        """Submit the completed journey to the sandbox."""
        return self.journey_service.submit_journey(lead_id, collected_fields)
