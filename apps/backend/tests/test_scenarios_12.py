"""
CIMET Reconnect — 12 Mandatory Scenario Tests (Phase 18)

Comprehensive automated test suite covering the 12 required hackathon evaluation scenarios:
1. Happy path (full end-to-end recovery + submission)
2. Misheard answer (clarify & resume)
3. Invalid answer (validation & retry)
4. Customer busy (polite decline)
5. Not interested (polite decline)
6. Frustration (immediate handoff)
7. Human request (immediate handoff)
8. Payment situation (payment boundary & handoff)
9. Off-script question (boundary & handoff)
10. Advice request (no advice boundary & handoff)
11. Low confidence (audio quality handoff)
12. Multiple retries (threshold escalation)
"""

import pytest
from app.agent.graph import EnergyRecoveryAgent
from app.domain.call_state import CallState
from app.domain.models import CallStatus, ConsentStatus, EscalationReason, JourneyStep
from app.services.dataset_adapter import MockDatasetAdapter


@pytest.fixture
def agent():
    return EnergyRecoveryAgent()


@pytest.fixture
def adapter():
    return MockDatasetAdapter()


# Scenario 1: Happy Path
def test_scenario_01_happy_path(agent, adapter):
    """Lead ENG-DEMO-003 resumes after usage_details, collects customer_details, and submits successfully."""
    lead = adapter.get_lead("ENG-DEMO-003")
    state = CallState.from_lead(lead)
    
    # Pre-fill previous step fields to simulate resumed state
    state.collected_fields = {
        "address": "42 Market Street", "suburb": "Melbourne", "postcode": "3000",
        "energy_type": "electricity", "electricity_meter_type": "smart", "has_solar": False,
        "electricity_usage": 950, "usage_period": "quarterly",
    }
    
    # 1. Start Call
    t0 = agent.start_call(state)
    assert t0["status"] == "active"
    assert "recorded" in t0["agent_message"].lower()
    
    # 2. Give Consent
    t1 = agent.process_turn(state, "Yes, that's fine, let's finish it up")
    assert t1["status"] == "active"
    assert state.consent_status == ConsentStatus.CONSENTED
    assert state.current_field == "first_name"

    # 3. Provide First Name
    t2 = agent.process_turn(state, "My name is David")
    assert t2["status"] == "active"
    assert state.collected_fields["first_name"] == "David"
    assert state.current_field == "last_name"

    # 4. Provide Last Name
    t3 = agent.process_turn(state, "My last name is Miller")
    assert t3["status"] == "active"
    assert state.collected_fields["last_name"] == "Miller"
    assert state.current_field == "email"

    # 5. Provide Email -> Complete & Submit
    t4 = agent.process_turn(state, "david.miller@example.com")
    assert t4["status"] == "completed"
    assert state.call_status == CallStatus.COMPLETED
    assert t4["submission_result"] is not None
    assert t4["submission_result"].status.value == "submitted"
    assert "reference" in t4["agent_message"].lower() or "cimet" in t4["agent_message"].lower()


# Scenario 2: Misheard Answer
def test_scenario_02_misheard_answer(agent, adapter):
    """Customer answers unclearly, gets asked for clarification, then answers clearly."""
    lead = adapter.get_lead("ENG-DEMO-003")
    state = CallState.from_lead(lead)
    state.mark_consent(ConsentStatus.CONSENTED)
    state.current_field = "first_name"

    # Unclear answer
    t1 = agent.process_turn(state, "err... umm... what?")
    assert t1["status"] == "active"
    assert state.retry_count == 1

    # Clarified answer
    t2 = agent.process_turn(state, "David")
    assert t2["status"] == "active"
    assert state.collected_fields["first_name"] == "David"
    assert state.retry_count == 0


# Scenario 3: Invalid Answer
def test_scenario_03_invalid_answer(agent, adapter):
    """Customer gives invalid postcode, gets corrective prompt, gives valid postcode."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)
    state.current_field = "postcode"

    # Invalid postcode (letters / wrong length)
    t1 = agent.process_turn(state, "My postcode is 999999")
    assert t1["status"] == "active"
    assert "postcode" not in state.collected_fields
    assert state.retry_count == 1

    # Valid postcode
    t2 = agent.process_turn(state, "Sorry, I meant 3000")
    assert t2["status"] == "active"
    assert state.collected_fields["postcode"] == "3000"


# Scenario 4: Customer Busy
def test_scenario_04_customer_busy(agent):
    """Customer says they are busy; call respectfully ends."""
    state = CallState(lead_id="ENG-DEMO-001")
    agent.start_call(state)

    t1 = agent.process_turn(state, "I'm really busy right now, don't call me")
    assert t1["status"] == "declined"
    assert state.call_status == CallStatus.DECLINED
    assert "goodbye" in t1["agent_message"].lower()


# Scenario 5: Not Interested
def test_scenario_05_not_interested(agent):
    """Customer declines consent with 'not interested'; call respectfully ends."""
    state = CallState(lead_id="ENG-DEMO-001")
    agent.start_call(state)

    t1 = agent.process_turn(state, "Not interested, please cancel my request")
    assert t1["status"] == "declined"
    assert state.call_status == CallStatus.DECLINED
    assert "goodbye" in t1["agent_message"].lower()


# Scenario 6: Frustration
def test_scenario_06_frustration(agent):
    """Customer expresses frustration; immediate escalation with handoff package."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)

    t1 = agent.process_turn(state, "This automated bot is completely useless and a waste of time!")
    assert t1["status"] == "handed_off"
    assert state.call_status == CallStatus.HANDOFF
    assert t1["handoff_package"].escalation_reason == EscalationReason.FRUSTRATION
    assert "specialist" in t1["agent_message"].lower() or "team" in t1["agent_message"].lower()


# Scenario 7: Human Request
def test_scenario_07_human_request(agent):
    """Customer explicitly asks for a human representative."""
    state = CallState(lead_id="ENG-DEMO-001")
    agent.start_call(state)

    t1 = agent.process_turn(state, "I don't want to talk to an AI, transfer me to a real person please")
    assert t1["status"] == "handed_off"
    assert state.call_status == CallStatus.HANDOFF
    assert t1["handoff_package"].escalation_reason == EscalationReason.HUMAN_REQUEST


# Scenario 8: Payment Situation
def test_scenario_08_payment_situation(agent):
    """Customer attempts to give credit card info; stop collection immediately and never store."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)

    t1 = agent.process_turn(state, "Can I pay for this right now with my credit card 4111 2222 3333 4444?")
    assert t1["status"] == "handed_off"
    assert state.call_status == CallStatus.HANDOFF
    assert t1["handoff_package"].escalation_reason == EscalationReason.PAYMENT
    # Verify zero credit card information is stored in collected_fields
    for val in state.collected_fields.values():
        assert "4111" not in str(val)
    assert "security" in t1["agent_message"].lower()


# Scenario 9: Off-Script Question
def test_scenario_09_off_script_question(agent):
    """Customer asks completely off-topic request."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)

    t1 = agent.process_turn(state, "Can you order a pizza for me right now?")
    assert t1["status"] == "handed_off"
    assert t1["handoff_package"].escalation_reason == EscalationReason.OFF_SCRIPT


# Scenario 10: Advice Request
def test_scenario_10_advice_request(agent):
    """Customer asks which energy provider to pick; AI does not advise, transfers to human."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)

    t1 = agent.process_turn(state, "Which provider should I choose between Origin and EnergyAustralia?")
    assert t1["status"] == "handed_off"
    assert t1["handoff_package"].escalation_reason == EscalationReason.ADVICE_REQUEST
    assert "advice" in t1["agent_message"].lower() or "specialist" in t1["agent_message"].lower()


# Scenario 11: Low Confidence
def test_scenario_11_low_confidence(agent):
    """Guardrail checks input with low confidence score and escalates."""
    state = CallState(lead_id="ENG-DEMO-001")
    res = agent.toolbox.guardrail_service.check("muffled sound [static]", confidence=0.40)
    assert res.passed is False
    assert res.escalation_reason == EscalationReason.LOW_CONFIDENCE


# Scenario 12: Multiple Retries Exceeded
def test_scenario_12_multiple_retries(agent):
    """Repeated failed inputs exceed max retries and escalate to human."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)
    state.current_field = "postcode"

    # Max retries is 2
    agent.process_turn(state, "bad input 1")
    assert state.retry_count == 1
    assert state.call_status == CallStatus.IN_PROGRESS

    t2 = agent.process_turn(state, "bad input 2")
    assert t2["status"] == "handed_off"
    assert state.call_status == CallStatus.HANDOFF
    assert t2["handoff_package"].escalation_reason == EscalationReason.REPEATED_FAILURE
