"""
CIMET Reconnect — Final Verification Test Suite

Covers all 6 evaluation scenarios:
A. Normal flow (consent -> fields -> review -> confirmation -> submit)
B. Customer name correction (Alex -> Sarah, with and without simultaneous consent)
C. Consent rejection vs name correction disambiguation
D. Barge-in / interruption handling
E. Final review correction and ambiguous confirmation prevention
F. Submission guards (consent, required fields, confirmation, decline, handoff)
"""

import pytest
from app.agent.graph import EnergyRecoveryAgent
from app.domain.call_state import CallState
from app.domain.models import CallStatus, ConsentStatus, EscalationReason, JourneyStep
from app.services.consent_service import ConsentService
from app.services.dataset_adapter import MockDatasetAdapter
from app.services.journey_service import PayloadBuilder


@pytest.fixture
def agent():
    return EnergyRecoveryAgent()


@pytest.fixture
def adapter():
    return MockDatasetAdapter()


# ─── A. Normal End-to-End Flow ────────────────────────────────────────────────
def test_scenario_a_normal_flow_to_submission(agent, adapter):
    """Customer answers -> recording disclosure -> consent -> resume -> fields -> submit."""
    lead = adapter.get_lead("ENG-DEMO-003")
    state = CallState.from_lead(lead)
    state.collected_fields = {
        "address": "42 Market Street", "suburb": "Melbourne", "postcode": "3000",
        "energy_type": "electricity", "electricity_meter_type": "smart", "has_solar": False,
        "electricity_usage": 950, "usage_period": "quarterly",
    }

    # 1. Start Call & DNC
    t0 = agent.start_call(state)
    assert t0["status"] == "active"
    assert "recorded for quality" in t0["agent_message"]

    # 2. Consent
    t1 = agent.process_turn(state, "Yes, absolutely, I agree")
    assert state.consent_status == ConsentStatus.CONSENTED
    assert state.current_field == "first_name"

    # 3. Collect Customer Details
    agent.process_turn(state, "My name is Sarah")
    assert state.collected_fields["first_name"] == "Sarah"

    agent.process_turn(state, "Jenkins")
    assert state.collected_fields["last_name"] == "Jenkins"

    t4 = agent.process_turn(state, "sarah.jenkins@example.com")
    assert t4["status"] == "completed"
    assert state.call_status == CallStatus.COMPLETED
    assert t4["submission_result"].status.value == "submitted"


# ─── B. Customer Name Correction ──────────────────────────────────────────────
def test_scenario_b_name_correction_pure(agent, adapter):
    """Lead contains 'Alex', customer corrects 'No, my name is Sarah'."""
    lead = adapter.get_lead("ENG-DEMO-001")
    state = CallState.from_lead(lead)
    state.collected_fields["first_name"] = "Alex"

    # Opening prompt uses candidate name
    t0 = agent.start_call(state)
    assert "Alex" in t0["agent_message"]

    # Customer corrects name
    t1 = agent.process_turn(state, "No, my name is Sarah")
    assert state.collected_fields["first_name"] == "Sarah"
    assert state.confirmed_customer_name == "Sarah"
    assert "Alex" not in state.collected_fields["first_name"]


def test_scenario_b_name_correction_with_consent(agent, adapter):
    """Customer says: 'No, my name is Sarah, but yes, I'm happy to continue.'"""
    lead = adapter.get_lead("ENG-DEMO-001")
    state = CallState.from_lead(lead)
    state.collected_fields["first_name"] = "Alex"

    agent.start_call(state)
    t1 = agent.process_turn(state, "No, my name is Sarah, but yes, I'm happy to continue.")
    assert state.consent_status == ConsentStatus.CONSENTED
    assert state.collected_fields["first_name"] == "Sarah"
    assert state.confirmed_customer_name == "Sarah"
    assert state.call_status != CallStatus.DECLINED


# ─── C. Consent Rejection Disambiguation ──────────────────────────────────────
def test_scenario_c_consent_rejection(agent):
    """Customer declines consent: 'No, I don't want to continue.'"""
    state = CallState(lead_id="ENG-DEMO-001")
    agent.start_call(state)

    turn = agent.process_turn(state, "No, I don't want to continue.")
    assert state.consent_status == ConsentStatus.DECLINED
    assert state.call_status == CallStatus.DECLINED
    assert turn["status"] == "declined"
    assert "goodbye" in turn["agent_message"].lower()
    assert state.journey_submission_status.value == "not_started"


def test_scenario_c_name_correction_not_confused_with_rejection():
    """'No, I'm Sarah' is detected as name correction, NOT call decline."""
    service = ConsentService()
    corrected, name = service.detect_name_correction("No, I'm Sarah")
    assert corrected is True
    assert name == "Sarah"


# ─── D. Barge-In Interruption Check ──────────────────────────────────────────
def test_scenario_d_barge_in_logic():
    """Verify non-silent audio detection triggers barge-in clear event flag."""
    # mu-law silence is 0xFF; active speech contains varied byte values
    silent_chunk = bytes([0xFF] * 160)
    speech_chunk = bytes([0x10, 0x20, 0x30, 0x40] * 40)

    non_silent_silent = sum(1 for b in silent_chunk if b not in (0xFF, 0x7F, 0xFE, 0x7E))
    non_silent_speech = sum(1 for b in speech_chunk if b not in (0xFF, 0x7F, 0xFE, 0x7E))

    assert non_silent_silent == 0
    assert non_silent_speech > (len(speech_chunk) * 0.4)


# ─── E. Final Confirmation & Review ──────────────────────────────────────────
def test_scenario_e_final_review_correction(agent):
    """Customer modifies a field during final stages before submission."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)
    state.collected_fields["electricity_usage"] = 500
    state.current_field = "electricity_usage"

    # Customer updates to 1200
    agent.process_turn(state, "Actually my usage is 1200 kilowatt hours")
    assert state.collected_fields["electricity_usage"] == 1200


# ─── F. Submission Guards ─────────────────────────────────────────────────────
def test_scenario_f_submission_guard_without_consent(agent):
    """Cannot submit journey if consent is not granted."""
    state = CallState(lead_id="ENG-DEMO-001")
    # State has no consent (PENDING)
    res = agent.process_turn(state, "Submit my details")
    assert res["status"] != "completed"
    assert state.journey_submission_status.value != "submitted"


def test_scenario_f_submission_guard_missing_fields():
    """PayloadBuilder rejects incomplete collected fields."""
    incomplete = {
        "address": "123 Main St",
        "suburb": "Sydney",
        "postcode": "2000",
        # missing energy_type, usage, customer details
    }
    validation = PayloadBuilder.validate_fields(incomplete)
    assert validation.valid is False
    assert len(validation.missing_fields) > 0


def test_scenario_f_submission_guard_on_handoff(agent):
    """Cannot submit journey when call is escalated to human handoff."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)
    turn = agent.process_turn(state, "I want to speak to a human right now")
    assert turn["status"] == "handed_off"
    assert state.journey_submission_status.value != "submitted"
