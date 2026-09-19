"""
CIMET Reconnect — LangGraph Agent Nodes

Node functions for the LangGraph recovery workflow.
Each node is a pure function that takes the workflow state, interacts via tools,
and returns the updated state.
"""

from typing import Any, Dict, Optional, TypedDict
from app.domain.call_state import CallState
from app.domain.models import CallStatus, ConsentStatus, EscalationReason, JourneyStep
from app.agent.tools import AgentToolbox
from app.services.consent_service import ConsentService
from app.services.guardrail_service import GuardrailCheckResult
from app.services.handoff_service import HandoffPackage
from app.services.journey_service import SubmissionResult


class AgentWorkflowState(TypedDict, total=False):
    """LangGraph agent state passed between graph nodes."""
    call_state: CallState
    customer_utterance: str
    confidence: Optional[float]
    agent_message: str
    status: str  # "active", "declined", "handed_off", "completed", "dnc_blocked"
    guardrail_result: Optional[GuardrailCheckResult]
    handoff_package: Optional[HandoffPackage]
    submission_result: Optional[SubmissionResult]
    next_node: Optional[str]


class AgentNodeHandler:
    """Encapsulates node execution logic with injected tools."""

    def __init__(self, toolbox: Optional[AgentToolbox] = None):
        self.toolbox = toolbox or AgentToolbox()

    def dnc_check_node(self, state: AgentWorkflowState) -> AgentWorkflowState:
        """Step 1: Check DNC list before proceeding with the call."""
        call_state = state["call_state"]
        phone = (
            call_state.to_phone
            or call_state.phone
            or call_state.reference_data.get("phone")
            or call_state.collected_fields.get("phone")
            or "+61400000001"
        )
        
        dnc_result = self.toolbox.check_dnc(phone)
        call_state.mark_dnc_checked(allowed=dnc_result.allowed)

        if not dnc_result.allowed:
            call_state.call_status = CallStatus.DECLINED
            return {
                **state,
                "call_state": call_state,
                "status": "dnc_blocked",
                "agent_message": "Number is on Do-Not-Call registry. Call terminated.",
                "next_node": "END",
            }

        # DNC passed -> proceed to consent
        candidate_name = (
            call_state.collected_fields.get("first_name")
            or call_state.collected_fields.get("customer_name")
            or call_state.reference_data.get("first_name")
            or call_state.reference_data.get("customer_name")
            or ""
        )
        consent_prompt = self.toolbox.consent_service.get_consent_prompt(candidate_name)
        return {
            **state,
            "call_state": call_state,
            "status": "active",
            "agent_message": consent_prompt,
            "next_node": "eval_consent",
        }

    def guardrail_node(self, state: AgentWorkflowState) -> AgentWorkflowState:
        """Step 2: Evaluate customer utterance against all 11 safety rules in priority order."""
        utterance = state.get("customer_utterance", "")
        confidence = state.get("confidence", 1.0)
        call_state = state["call_state"]

        guardrail_result = self.toolbox.check_guardrails(utterance, confidence=confidence)

        # 1. Customer Decline / Busy during active conversation -> respectful exit
        if guardrail_result.violation_rule == "customer_decline":
            call_state.call_status = CallStatus.DECLINED
            if call_state.consent_status == ConsentStatus.PENDING:
                call_state.consent_status = ConsentStatus.DECLINED
            return {
                **state,
                "call_state": call_state,
                "guardrail_result": guardrail_result,
                "status": "declined",
                "agent_message": guardrail_result.agent_message or "No problem at all. Thank you, goodbye!",
                "next_node": "END",
            }


        # 2. Customer Confusion: clarifies question up to max_retries, then escalates to human
        if guardrail_result.escalation_reason == EscalationReason.CONFUSION:
            if not call_state.has_exceeded_retries():
                call_state.increment_retry()
                target_field = call_state.current_field or self._get_next_field_to_ask(call_state)
                q = self._get_field_question(target_field, call_state) if target_field else "Could you please confirm your details?"
                clarification = f"No worries at all, let me clarify. {q}"
                return {
                    **state,
                    "call_state": call_state,
                    "guardrail_result": guardrail_result,
                    "status": "active",
                    "agent_message": clarification,
                    "next_node": "await_field_input",
                }
            else:
                handoff = self.toolbox.create_handoff(
                    call_state=call_state,
                    reason=EscalationReason.CONFUSION,
                    customer_statement=guardrail_result.customer_statement,
                    summary=f"Customer expressed repeated confusion during step '{call_state.current_step.value}'.",
                )
                return {
                    **state,
                    "call_state": call_state,
                    "guardrail_result": guardrail_result,
                    "handoff_package": handoff,
                    "status": "handed_off",
                    "agent_message": guardrail_result.agent_message or "Connecting you to a specialist.",
                    "next_node": "END",
                }

        # 3. All other safety escalations -> immediate handoff package
        if guardrail_result.escalation_required:
            handoff = self.toolbox.create_handoff(
                call_state=call_state,
                reason=guardrail_result.escalation_reason,
                customer_statement=guardrail_result.customer_statement,
            )
            return {
                **state,
                "call_state": call_state,
                "guardrail_result": guardrail_result,
                "handoff_package": handoff,
                "status": "handed_off",
                "agent_message": guardrail_result.agent_message or "Connecting you to a specialist.",
                "next_node": "END",
            }

        return {
            **state,
            "guardrail_result": guardrail_result,
            "next_node": "process_input",
        }

    def consent_node(self, state: AgentWorkflowState) -> AgentWorkflowState:
        """Step 3: Process consent response and verify/confirm customer identity."""
        utterance = state.get("customer_utterance", "")
        call_state = state["call_state"]

        consent_eval = self.toolbox.evaluate_consent(utterance)
        call_state.mark_consent(consent_eval.status)

        # Check if customer corrected or stated their name in this turn
        corrected, new_name = ConsentService.detect_name_correction(utterance)
        name_prefix = ""
        if corrected and new_name:
            call_state.collected_fields["first_name"] = new_name
            call_state.confirmed_customer_name = new_name
            call_state.customer_name_confirmed = True
            name_prefix = f"Nice to meet you, {new_name}! "
        elif consent_eval.status == ConsentStatus.CONSENTED:
            candidate_name = (
                call_state.collected_fields.get("first_name")
                or call_state.reference_data.get("first_name")
            )
            if candidate_name and not call_state.customer_name_confirmed:
                call_state.collected_fields["first_name"] = candidate_name
                call_state.confirmed_customer_name = candidate_name
                call_state.customer_name_confirmed = True

        if consent_eval.status == ConsentStatus.DECLINED:
            call_state.call_status = CallStatus.DECLINED
            return {
                **state,
                "call_state": call_state,
                "status": "declined",
                "agent_message": consent_eval.response_script,
                "next_node": "END",
            }
        elif consent_eval.status == ConsentStatus.CONSENTED:
            # Determine next missing field to collect
            next_field_name = self._get_next_field_to_ask(call_state)
            call_state.current_field = next_field_name

            if next_field_name:
                question = self._get_field_question(next_field_name, call_state)
                opening_message = (
                    f"{name_prefix}Great, thank you! I see you started an energy comparison with us. "
                    f"Let's quickly finish up the remaining details. {question}"
                )
            else:
                opening_message = f"{name_prefix}Thank you. It looks like all your details are complete!"

            return {
                **state,
                "call_state": call_state,
                "status": "active",
                "agent_message": opening_message,
                "next_node": "await_field_input",
            }
        else:
            # Ambiguous consent -> ask to clarify
            return {
                **state,
                "call_state": call_state,
                "status": "active",
                "agent_message": consent_eval.response_script,
                "next_node": "eval_consent",
            }

    def process_field_node(self, state: AgentWorkflowState) -> AgentWorkflowState:
        """Step 4: Extract and validate field value from utterance."""
        call_state = state["call_state"]
        utterance = state.get("customer_utterance", "")

        # Mandatory Consent Enforcement: Zero data collection permitted prior to explicit consent
        if call_state.consent_status != ConsentStatus.CONSENTED:
            return self.consent_node(state)

        target_field = call_state.current_field or self._get_next_field_to_ask(call_state)
        if not target_field:
            # No more fields needed -> transition to completion
            return self.submit_journey_node(state)

        # Spontaneous name correction check during general turns
        corrected, new_name = ConsentService.detect_name_correction(utterance)
        if corrected and new_name and target_field != "first_name":
            call_state.collected_fields["first_name"] = new_name
            call_state.confirmed_customer_name = new_name
            call_state.customer_name_confirmed = True

        ref_val = call_state.reference_data.get(target_field)
        extracted = self.toolbox.extract_and_validate_field(
            target_field, utterance, reference_value=ref_val
        )

        if extracted.is_valid:
            # Field valid -> Save to state
            call_state.save_field(target_field, extracted.raw_value, confidence=extracted.confidence)
            if extracted.unit:
                call_state.collected_fields[f"{target_field}_unit"] = extracted.unit

            # Check if current step is now complete
            step_fields = self.toolbox.script_engine.get_fields_for_step(call_state.current_step)
            step_field_names = [f.name for f in step_fields]
            if all(f in call_state.collected_fields for f in step_field_names):
                # Advance step
                next_step = self._get_next_journey_step(call_state.current_step)
                if next_step:
                    call_state.advance_step(next_step)

            # Find next field to ask
            next_field = self._get_next_field_to_ask(call_state)
            call_state.current_field = next_field

            if next_field:
                question = self._get_field_question(next_field, call_state)
                if target_field == "electricity_usage" and extracted.display_value:
                    ack = f"Got it — {extracted.display_value}. Is that your monthly or quarterly usage?"
                elif target_field == "has_solar":
                    solar_ack = "solar panels included" if extracted.raw_value is True else "no solar"
                    ack = f"Got it, {solar_ack}. {question}"
                elif target_field == "electricity_meter_type":
                    meter_ack = "no problem" if extracted.raw_value == "unknown" else str(extracted.raw_value).replace("_", " ")
                    ack = f"Got it, {meter_ack}. {question}"
                elif extracted.display_value:
                    ack = f"Got it, {extracted.display_value}. {question}"
                else:
                    ack = f"Got it, {extracted.raw_value}. {question}"
                return {
                    **state,
                    "call_state": call_state,
                    "status": "active",
                    "agent_message": ack,
                    "next_node": "await_field_input",
                }
            else:
                # All fields collected! Proceed to submit
                return self.submit_journey_node(state)
        else:
            # Field invalid -> increment retry
            call_state.increment_retry()
            if call_state.has_exceeded_retries():
                # Max retries exceeded -> escalate
                handoff = self.toolbox.create_handoff(
                    call_state=call_state,
                    reason=EscalationReason.REPEATED_FAILURE,
                    customer_statement=utterance,
                    summary=f"Failed validation on field '{target_field}' after {call_state.retry_count} retries.",
                )
                return {
                    **state,
                    "call_state": call_state,
                    "handoff_package": handoff,
                    "status": "handed_off",
                    "agent_message": (
                        f"I'm having a little trouble with the {target_field.replace('_', ' ')}. "
                        "Let me connect you with a specialist to finalize this quickly for you."
                    ),
                    "next_node": "END",
                }
            else:
                # Ask again with helpful format hint
                question = self._get_field_question(target_field, call_state)
                hint = f" ({extracted.validation_error})" if extracted.validation_error else ""
                re_prompt = f"Sorry, I didn't quite catch that{hint}. {question}"
                return {
                    **state,
                    "call_state": call_state,
                    "status": "active",
                    "agent_message": re_prompt,
                    "next_node": "await_field_input",
                }

    def submit_journey_node(self, state: AgentWorkflowState) -> AgentWorkflowState:
        """Step 5: All required fields collected -> build and submit payload."""
        call_state = state["call_state"]
        result = self.toolbox.submit_journey(call_state.lead_id, call_state.collected_fields)

        if result.status.value == "submitted":
            call_state.complete_journey()
            call_state.mark_submitted(success=True)
            closing_msg = (
                f"Thank you so much! All your details have been confirmed and your energy comparison "
                f"journey has been successfully submitted (Reference: {result.reference_id}). "
                "You'll receive an email confirmation shortly. Have a wonderful day!"
            )
            return {
                **state,
                "call_state": call_state,
                "submission_result": result,
                "status": "completed",
                "agent_message": closing_msg,
                "next_node": "END",
            }
        else:
            # Downstream failure -> escalate to human
            handoff = self.toolbox.create_handoff(
                call_state=call_state,
                reason=EscalationReason.NONE,
                customer_statement="System submission error",
                summary=f"Journey payload submission failed: {result.message}",
            )
            return {
                **state,
                "call_state": call_state,
                "submission_result": result,
                "handoff_package": handoff,
                "status": "handed_off",
                "agent_message": "All your information is saved, and a specialist will review and finalize your submission.",
                "next_node": "END",
            }

    def _get_field_question(self, field_name: str, call_state: CallState) -> str:
        """Get the question for a field, forming a confirmation question if reference data already exists."""
        ref_val = call_state.reference_data.get(field_name)
        if ref_val is not None and str(ref_val).strip() != "":
            if field_name == "email":
                return f"I have your email as {ref_val}, is that still correct?"
            elif field_name == "last_name":
                return f"I have your last name as {ref_val}, is that correct?"
            elif field_name == "first_name":
                return f"I have your first name as {ref_val}, is that correct?"
            elif field_name == "phone":
                return f"I have your phone number as {ref_val}, is that correct?"
            elif field_name == "address":
                return f"I have your address as {ref_val}, is that correct?"
            elif field_name == "suburb":
                return f"I have your suburb as {ref_val}, is that correct?"
            elif field_name == "postcode":
                return f"I have your postcode as {ref_val}, is that correct?"
            else:
                display_name = field_name.replace("_", " ")
                return f"I have your {display_name} as {ref_val}, is that correct?"

        field_def = self.toolbox.script_engine.get_field(field_name)
        return field_def.question if field_def else f"Could you provide your {field_name.replace('_', ' ')}?"

    def _get_next_field_to_ask(self, call_state: CallState) -> Optional[str]:
        """Determine next uncollected field in sequence, skipping completed steps."""
        for field_def in self.toolbox.script_engine.all_fields:
            if field_def.step in call_state.completed_steps:
                continue
            if field_def.name not in call_state.collected_fields:
                return field_def.name
        return None

    def _get_next_journey_step(self, current: JourneyStep) -> Optional[JourneyStep]:
        """Get next step in journey sequence."""
        order = [
            JourneyStep.PROPERTY_DETAILS,
            JourneyStep.ENERGY_DETAILS,
            JourneyStep.USAGE_DETAILS,
            JourneyStep.CUSTOMER_DETAILS,
            JourneyStep.COMPLETION,
        ]
        try:
            idx = order.index(current)
            if idx + 1 < len(order):
                return order[idx + 1]
        except ValueError:
            pass
        return None
