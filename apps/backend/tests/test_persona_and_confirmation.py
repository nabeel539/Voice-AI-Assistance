"""
Tests for Agent Persona ("Emma from CIMET"), Customer Identity Verification & Name Corrections.
"""

import pytest
from app.agent.graph import EnergyRecoveryAgent
from app.domain.call_state import CallState
from app.domain.models import CallStatus, ConsentStatus
from app.services.consent_service import ConsentService
from app.services.dataset_adapter import MockDatasetAdapter


@pytest.fixture
def agent():
    return EnergyRecoveryAgent()


@pytest.fixture
def adapter():
    return MockDatasetAdapter()


def test_persona_opening_with_candidate_name(agent, adapter):
    """Verify agent opens with warm 'Emma from CIMET' persona and candidate reference name."""
    lead = adapter.get_lead("ENG-DEMO-001")
    state = CallState.from_lead(lead)
    state.collected_fields["first_name"] = "Alex"

    start_res = agent.start_call(state)
    msg = start_res["agent_message"]

    assert "Emma here from CIMET" in msg
    assert "Hey Alex" in msg
    assert "recorded" in msg.lower()
    assert "happy to go ahead" in msg.lower() or "continue" in msg.lower()
    # Name is not marked confirmed until customer acknowledges
    assert state.customer_name_confirmed is False


def test_persona_opening_without_candidate_name(agent, adapter):
    """Verify agent opens politely with 'Hey there' when no candidate name is in lead data."""
    lead = adapter.get_lead("ENG-DEMO-001")
    state = CallState.from_lead(lead)
    state.collected_fields.pop("first_name", None)
    state.collected_fields.pop("customer_name", None)
    state.reference_data.clear()

    start_res = agent.start_call(state)
    msg = start_res["agent_message"]

    assert "Emma here from CIMET" in msg
    assert "Hey there" in msg
    assert "recorded" in msg.lower()


def test_customer_confirms_candidate_name(agent, adapter):
    """Verify customer agreeing confirms the reference candidate name."""
    lead = adapter.get_lead("ENG-DEMO-001")
    state = CallState.from_lead(lead)
    state.collected_fields["first_name"] = "Alex"

    agent.start_call(state)
    turn1 = agent.process_turn(state, "Yes, that's fine, I'm happy to continue")

    assert state.consent_status == ConsentStatus.CONSENTED
    assert state.customer_name_confirmed is True
    assert state.confirmed_customer_name == "Alex"
    assert state.collected_fields["first_name"] == "Alex"


def test_customer_corrects_name_during_consent(agent, adapter):
    """Verify customer stating their name is different updates state and agent adopts the new name."""
    lead = adapter.get_lead("ENG-DEMO-001")
    state = CallState.from_lead(lead)
    state.collected_fields["first_name"] = "Alex"  # Reference candidate from lead

    agent.start_call(state)
    # Customer says they are Sarah, not Alex
    turn1 = agent.process_turn(state, "No my name is Sarah, but yes I'm happy to continue")

    assert state.consent_status == ConsentStatus.CONSENTED
    assert state.customer_name_confirmed is True
    assert state.confirmed_customer_name == "Sarah"
    assert state.collected_fields["first_name"] == "Sarah"
    assert "Nice to meet you, Sarah!" in turn1["agent_message"]


def test_customer_corrects_name_with_i_am(agent, adapter):
    """Verify 'I am Jordan' updates identity properly."""
    lead = adapter.get_lead("ENG-DEMO-002")
    state = CallState.from_lead(lead)

    agent.start_call(state)
    turn1 = agent.process_turn(state, "Sure thing, but I am Jordan")

    assert state.consent_status == ConsentStatus.CONSENTED
    assert state.confirmed_customer_name == "Jordan"
    assert state.collected_fields["first_name"] == "Jordan"
    assert "Nice to meet you, Jordan!" in turn1["agent_message"]


def test_detect_name_correction_helper():
    """Unit test the regex detector for various natural speech patterns."""
    assert ConsentService.detect_name_correction("No, my name is Michael") == (True, "Michael")
    assert ConsentService.detect_name_correction("Actually it's Samantha") == (True, "Samantha")
    assert ConsentService.detect_name_correction("This is David speaking") == (True, "David")
    assert ConsentService.detect_name_correction("I am Robert, yes continue") == (True, "Robert")
    assert ConsentService.detect_name_correction("Not Alex, it's Sarah") == (True, "Sarah")
    assert ConsentService.detect_name_correction("Yes sure go ahead") == (False, None)
    assert ConsentService.detect_name_correction("No I'm not interested") == (False, None)
