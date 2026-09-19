"""
CIMET Reconnect — Tests for Services & LangGraph Agent

Tests for:
- Phase 6: LangGraph Agent workflow
- Phase 7: DNC Service
- Phase 8: Consent Service
- Phase 9: Voice Services (STT, LLM, TTS)
- Phase 11: Structured Extraction Service
- Phase 12: Guardrails Service (11 safety rules)
- Phase 13: Human Handoff Service
- Phase 14: Journey Service & PayloadBuilder
"""

import pytest
from app.agent.graph import EnergyRecoveryAgent, build_recovery_graph
from app.agent.tools import AgentToolbox
from app.domain.call_state import CallState
from app.domain.models import CallStatus, ConsentStatus, EscalationReason, JourneyStep, Lead
from app.services.consent_service import ConsentService
from app.services.dataset_adapter import MockDatasetAdapter
from app.services.dnc_service import MockDNCService
from app.services.extraction_service import ExtractionService
from app.services.guardrail_service import GuardrailService
from app.services.handoff_service import HandoffService
from app.services.journey_service import MockJourneyService, PayloadBuilder
from app.services.llm_service import MockLLMService
from app.services.script_engine import ScriptEngine
from app.services.stt_service import MockSTTService
from app.services.tts_service import MockTTSService


# ==============================================================================
# Phase 7: DNC Service Tests
# ==============================================================================

class TestDNCService:
    def test_allowed_number(self):
        dnc = MockDNCService()
        res = dnc.check("+61412345678")
        assert res.allowed is True

    def test_blocked_number_in_default_list(self):
        dnc = MockDNCService()
        res = dnc.check("+61400000999")
        assert res.allowed is False
        assert "Do-Not-Call" in res.reason

    def test_block_and_unblock_number(self):
        dnc = MockDNCService()
        num = "+61411111111"
        assert dnc.check(num).allowed is True
        dnc.block_number(num)
        assert dnc.check(num).allowed is False
        dnc.unblock_number(num)
        assert dnc.check(num).allowed is True


# ==============================================================================
# Phase 8: Consent Service Tests
# ==============================================================================

class TestConsentService:
    def test_affirmative_consent(self):
        service = ConsentService()
        for phrase in ["Yes please", "sure go ahead", "ok, that's fine", "yeah no problem", "I agree"]:
            res = service.evaluate(phrase)
            assert res.status == ConsentStatus.CONSENTED, f"Failed for: {phrase}"

    def test_declined_consent(self):
        service = ConsentService()
        for phrase in ["No thanks", "not interested", "stop calling me", "hang up", "no recording please"]:
            res = service.evaluate(phrase)
            assert res.status == ConsentStatus.DECLINED, f"Failed for: {phrase}"
            assert "goodbye" in res.response_script.lower()

    def test_unclear_consent(self):
        service = ConsentService()
        res = service.evaluate("Who is this again?")
        assert res.status == ConsentStatus.PENDING


# ==============================================================================
# Phase 12: Guardrails Service Tests (All 11 Guardrails)
# ==============================================================================

class TestGuardrailsService:
    @pytest.fixture
    def guardrails(self):
        return GuardrailService()

    def test_payment_card_guardrail(self, guardrails):
        res = guardrails.check("Here is my credit card 4532 1234 5678 9010")
        assert res.passed is False
        assert res.escalation_required is True
        assert res.escalation_reason == EscalationReason.PAYMENT

    def test_payment_cvv_guardrail(self, guardrails):
        res = guardrails.check("My cvv is 123 and expiry is next year")
        assert res.passed is False
        assert res.escalation_reason == EscalationReason.PAYMENT

    def test_human_request_guardrail(self, guardrails):
        res = guardrails.check("Can I please speak to a human agent?")
        assert res.passed is False
        assert res.escalation_required is True
        assert res.escalation_reason == EscalationReason.HUMAN_REQUEST

    def test_frustration_guardrail(self, guardrails):
        res = guardrails.check("This is ridiculous, stop wasting my time!")
        assert res.passed is False
        assert res.escalation_reason == EscalationReason.FRUSTRATION

    def test_confusion_guardrail(self, guardrails):
        res = guardrails.check("I don't understand what you mean at all.")
        assert res.passed is False
        assert res.escalation_reason == EscalationReason.CONFUSION

    def test_no_advice_guardrail(self, guardrails):
        res = guardrails.check("Which provider should I choose between AGL and Origin?")
        assert res.passed is False
        assert res.escalation_reason == EscalationReason.ADVICE_REQUEST

    def test_sensitive_situation_bereavement(self, guardrails):
        res = guardrails.check("My husband recently passed away and I am handling his estate")
        assert res.passed is False
        assert res.escalation_reason == EscalationReason.SENSITIVE

    def test_sensitive_situation_hardship(self, guardrails):
        res = guardrails.check("I am having extreme financial hardship and cannot afford groceries")
        assert res.passed is False
        assert res.escalation_reason == EscalationReason.SENSITIVE

    def test_off_script_guardrail(self, guardrails):
        res = guardrails.check("Can you book a flight to Melbourne for tomorrow?")
        assert res.passed is False
        assert res.escalation_reason == EscalationReason.OFF_SCRIPT

    def test_low_confidence_guardrail(self, guardrails):
        res = guardrails.check("muffled static sound", confidence=0.45)
        assert res.passed is False
        assert res.escalation_reason == EscalationReason.LOW_CONFIDENCE

    def test_valid_normal_speech_passes(self, guardrails):
        res = guardrails.check("My postcode is 3000")
        assert res.passed is True
        assert res.escalation_required is False
        assert res.escalation_reason == EscalationReason.NONE


# ==============================================================================
# Phase 13: Human Handoff Service Tests
# ==============================================================================

class TestHandoffService:
    def test_create_handoff_package(self):
        handoff_srv = HandoffService()
        call_state = CallState(lead_id="ENG-DEMO-001")
        call_state.collected_fields = {"address": "123 Main St", "suburb": "Brisbane"}

        package = handoff_srv.create_handoff(
            call_state=call_state,
            reason=EscalationReason.HUMAN_REQUEST,
            customer_statement="I want to speak with someone",
        )

        assert package.lead_id == "ENG-DEMO-001"
        assert package.escalation_reason == EscalationReason.HUMAN_REQUEST
        assert package.collected_fields["suburb"] == "Brisbane"
        assert package.suggested_operator_action != ""
        assert call_state.call_status == CallStatus.HANDOFF


# ==============================================================================
# Phase 14: Journey Service & PayloadBuilder Tests
# ==============================================================================

class TestJourneyService:
    def test_payload_builder_missing_fields(self):
        fields = {"address": "123 Main St"}
        res = PayloadBuilder.validate_fields(fields)
        assert res.valid is False
        assert len(res.missing_fields) > 0

    def test_payload_builder_all_fields(self):
        complete_fields = {
            "address": "123 George Street",
            "suburb": "Brisbane",
            "postcode": "4000",
            "energy_type": "both",
            "electricity_meter_type": "smart",
            "has_solar": False,
            "electricity_usage": 1200,
            "usage_period": "quarterly",
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane.doe@example.com",
        }
        res = PayloadBuilder.validate_fields(complete_fields)
        assert res.valid is True

        payload = PayloadBuilder.build("ENG-DEMO-001", complete_fields)
        assert payload.lead_id == "ENG-DEMO-001"
        assert payload.property_details["postcode"] == "4000"
        assert payload.customer_details["email"] == "jane.doe@example.com"

    def test_mock_journey_service_submission(self):
        service = MockJourneyService()
        complete_fields = {
            "address": "123 George Street", "suburb": "Brisbane", "postcode": "4000",
            "energy_type": "both", "electricity_meter_type": "smart", "has_solar": False,
            "electricity_usage": 1200, "usage_period": "quarterly",
            "first_name": "Jane", "last_name": "Doe", "email": "jane.doe@example.com",
        }
        res = service.submit_journey("ENG-DEMO-001", complete_fields)
        assert res.status.value == "submitted"
        assert res.reference_id.startswith("CIMET-REC-")
        assert len(service.submissions) == 1


# ==============================================================================
# Phase 11: Structured Extraction Service Tests
# ==============================================================================

class TestExtractionService:
    @pytest.fixture
    def extraction(self):
        script_eng = ScriptEngine()
        return ExtractionService(script_eng)

    def test_extract_postcode(self, extraction):
        res = extraction.extract_field("postcode", "I am currently living at 3000 Melbourne")
        assert res.is_valid is True
        assert res.raw_value == "3000"

    def test_extract_invalid_postcode(self, extraction):
        res = extraction.extract_field("postcode", "My postcode is 123456")
        assert res.is_valid is False

    def test_extract_email(self, extraction):
        res = extraction.extract_field("email", "You can reach me at john.smith@gmail.com please")
        assert res.is_valid is True
        assert res.raw_value == "john.smith@gmail.com"

    def test_extract_solar_boolean(self, extraction):
        res_yes = extraction.extract_field("has_solar", "Yes we installed solar panels last year")
        assert res_yes.is_valid is True
        assert res_yes.raw_value is True

        res_no = extraction.extract_field("has_solar", "No we don't have any solar")
        assert res_no.is_valid is True
        assert res_no.raw_value is False

    def test_extract_energy_type(self, extraction):
        res = extraction.extract_field("energy_type", "We need both electricity and gas")
        assert res.is_valid is True
        assert res.raw_value == "both"


# ==============================================================================
# Phase 9: Voice Services (Mocked) Tests
# ==============================================================================

class TestVoiceServices:
    def test_mock_stt(self):
        stt = MockSTTService("Hello from test")
        res = stt.transcribe(b"fake-audio")
        assert res.text == "Hello from test"

    def test_mock_llm(self):
        llm = MockLLMService("AI response")
        res = llm.generate_chat_response([{"role": "user", "content": "Hi"}])
        assert res == "AI response"

    def test_mock_tts(self):
        tts = MockTTSService()
        audio = tts.synthesize("Hello")
        assert len(audio) > 0


# ==============================================================================
# Phase 6: LangGraph Agent Tests
# ==============================================================================

class TestLangGraphAgent:
    def test_start_call_prompts_consent(self):
        agent = EnergyRecoveryAgent()
        call_state = CallState(lead_id="ENG-DEMO-001")
        result = agent.start_call(call_state)

        assert result["status"] == "active"
        assert "recorded" in result["agent_message"].lower()

    def test_customer_declines_consent(self):
        agent = EnergyRecoveryAgent()
        call_state = CallState(lead_id="ENG-DEMO-001")
        agent.start_call(call_state)

        turn_result = agent.process_turn(call_state, "No thanks, I don't want to do this")
        assert turn_result["status"] == "declined"
        assert call_state.consent_status == ConsentStatus.DECLINED
        assert "goodbye" in turn_result["agent_message"].lower()

    def test_customer_accepts_consent_and_resumes(self):
        agent = EnergyRecoveryAgent()
        # ENG-DEMO-003 has completed property, energy, and usage details; only customer details remain
        adapter = MockDatasetAdapter()
        lead = adapter.get_lead("ENG-DEMO-003")
        call_state = CallState.from_lead(lead)
        agent.start_call(call_state)

        turn_result = agent.process_turn(call_state, "Yes that's fine, let's continue")
        assert turn_result["status"] == "active"
        assert call_state.consent_status == ConsentStatus.CONSENTED
        # Should ask for next missing field (first_name)
        assert call_state.current_field == "first_name"
        assert "first" in turn_result["agent_message"].lower() or "name" in turn_result["agent_message"].lower()

    def test_guardrail_triggers_handoff_in_agent(self):
        agent = EnergyRecoveryAgent()
        call_state = CallState(lead_id="ENG-DEMO-001")
        agent.start_call(call_state)

        turn_result = agent.process_turn(call_state, "I want to pay right now, here is my visa 4532 1234 5678 9010")
        assert turn_result["status"] == "handed_off"
        assert turn_result["handoff_package"] is not None
        assert turn_result["handoff_package"].escalation_reason == EscalationReason.PAYMENT
        assert "security" in turn_result["agent_message"].lower() or "specialist" in turn_result["agent_message"].lower()

    def test_repeated_failure_escalation_in_agent(self):
        agent = EnergyRecoveryAgent()
        call_state = CallState(lead_id="ENG-DEMO-001")
        call_state.mark_consent(ConsentStatus.CONSENTED)
        call_state.current_field = "postcode"

        # Try invalid postcodes up to retry limit
        agent.process_turn(call_state, "postcode is ABCDE")  # retry 1
        turn2 = agent.process_turn(call_state, "invalid again")  # retry 2 (max_retries is 2)

        assert turn2["status"] == "handed_off"
        assert turn2["handoff_package"].escalation_reason == EscalationReason.REPEATED_FAILURE

    def test_electricity_usage_preserves_unit_and_numeric_payload(self):
        """Regression test: Customer gives 'My usage is about 1200 kilowatt hours.'
        1. Numerical value stored in state is integer 1200 (not 1200.0, not dollar).
        2. Unit 'kWh' is preserved in collected state.
        3. Conversational response preserves unit:
           'Got it — about 1,200 kilowatt hours. Is that your monthly or quarterly usage?'
        """
        agent = EnergyRecoveryAgent()
        call_state = CallState(
            lead_id="ENG-DEMO-001",
            completed_steps=[JourneyStep.PROPERTY_DETAILS, JourneyStep.ENERGY_DETAILS],
            current_step=JourneyStep.USAGE_DETAILS,
            current_field="electricity_usage",
        )
        call_state.mark_consent(ConsentStatus.CONSENTED)

        turn = agent.process_turn(call_state, "My usage is about 1200 kilowatt hours.")

        assert turn["status"] == "active"
        # 1. Stored numerical value must be 1200 (integer)
        assert call_state.collected_fields["electricity_usage"] == 1200
        assert isinstance(call_state.collected_fields["electricity_usage"], int)

        # 2. Unit must be preserved
        assert call_state.collected_fields.get("electricity_usage_unit") == "kWh"

        # 3. Conversational response must preserve unit and context
        expected_response = "Got it — about 1,200 kilowatt hours. Is that your monthly or quarterly usage?"
        assert turn["agent_message"] == expected_response

        # 4. Advances to next field
        assert call_state.current_field == "usage_period"
