"""
Tests for Phases 2-5: Dataset Adapter, Script Engine, and Call State.
"""

import json
import tempfile
from pathlib import Path

import pytest

from app.domain.models import (
    JourneyStep,
    Lead,
    ConsentStatus,
    EscalationReason,
    CallStatus,
    JOURNEY_STEP_ORDER,
)
from app.domain.call_state import CallState
from app.services.dataset_adapter import MockDatasetAdapter
from app.services.script_engine import ScriptEngine


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2 — Dataset Adapter Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMockDatasetAdapter:
    """Test the MockDatasetAdapter."""

    def test_load_leads_returns_list(self):
        adapter = MockDatasetAdapter()
        leads = adapter.load_leads()
        assert isinstance(leads, list)
        assert len(leads) > 0

    def test_load_leads_returns_lead_models(self):
        adapter = MockDatasetAdapter()
        leads = adapter.load_leads()
        for lead in leads:
            assert isinstance(lead, Lead)

    def test_load_leads_count(self):
        adapter = MockDatasetAdapter()
        leads = adapter.load_leads()
        assert len(leads) == 8  # 8 leads in mock dataset

    def test_get_lead_by_id(self):
        adapter = MockDatasetAdapter()
        lead = adapter.get_lead("ENG-DEMO-001")
        assert lead is not None
        assert lead.lead_id == "ENG-DEMO-001"
        assert lead.last_completed_step == JourneyStep.PROPERTY_DETAILS

    def test_get_lead_returns_none_for_missing(self):
        adapter = MockDatasetAdapter()
        lead = adapter.get_lead("NONEXISTENT")
        assert lead is None

    def test_lead_step_mapping(self):
        adapter = MockDatasetAdapter()
        lead_002 = adapter.get_lead("ENG-DEMO-002")
        assert lead_002.last_completed_step == JourneyStep.ENERGY_DETAILS

        lead_003 = adapter.get_lead("ENG-DEMO-003")
        assert lead_003.last_completed_step == JourneyStep.USAGE_DETAILS

    def test_lead_next_step(self):
        adapter = MockDatasetAdapter()
        lead = adapter.get_lead("ENG-DEMO-001")
        next_step = lead.get_next_step()
        assert next_step == JourneyStep.ENERGY_DETAILS

    def test_custom_data_path(self):
        # Create a temp file with custom data
        data = [{"lead_id": "TEST-001", "last_completed_step": "property_details", "test_contact": "+61400000099"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            temp_path = Path(f.name)

        adapter = MockDatasetAdapter(data_path=temp_path)
        leads = adapter.load_leads()
        assert len(leads) == 1
        assert leads[0].lead_id == "TEST-001"

        temp_path.unlink()

    def test_missing_file_raises_error(self):
        adapter = MockDatasetAdapter(data_path=Path("/nonexistent/path.json"))
        with pytest.raises(FileNotFoundError):
            adapter.load_leads()


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3 & 4 — Script Engine Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestScriptEngine:
    """Test the ScriptEngine."""

    @pytest.fixture
    def engine(self):
        return ScriptEngine()

    def test_loads_all_fields(self, engine):
        assert len(engine.all_fields) == 11

    def test_property_details_fields(self, engine):
        fields = engine.get_fields_for_step(JourneyStep.PROPERTY_DETAILS)
        names = [f.name for f in fields]
        assert "address" in names
        assert "suburb" in names
        assert "postcode" in names

    def test_energy_details_fields(self, engine):
        fields = engine.get_fields_for_step(JourneyStep.ENERGY_DETAILS)
        names = [f.name for f in fields]
        assert "energy_type" in names
        assert "electricity_meter_type" in names
        assert "has_solar" in names

    def test_usage_details_fields(self, engine):
        fields = engine.get_fields_for_step(JourneyStep.USAGE_DETAILS)
        names = [f.name for f in fields]
        assert "electricity_usage" in names
        assert "usage_period" in names

    def test_customer_details_fields(self, engine):
        fields = engine.get_fields_for_step(JourneyStep.CUSTOMER_DETAILS)
        names = [f.name for f in fields]
        assert "first_name" in names
        assert "last_name" in names
        assert "email" in names

    def test_get_field_by_name(self, engine):
        field = engine.get_field("postcode")
        assert field is not None
        assert field.name == "postcode"
        assert field.step == JourneyStep.PROPERTY_DETAILS

    def test_get_missing_fields(self, engine):
        collected = {"address": "123 George St", "suburb": "Brisbane"}
        missing = engine.get_missing_fields(JourneyStep.PROPERTY_DETAILS, collected)
        assert len(missing) == 1
        assert missing[0].name == "postcode"

    def test_get_next_field(self, engine):
        collected = {"address": "123 George St"}
        next_field = engine.get_next_field(JourneyStep.PROPERTY_DETAILS, collected)
        assert next_field.name == "suburb"

    def test_step_complete(self, engine):
        collected = {"address": "123 George St", "suburb": "Brisbane", "postcode": "4000"}
        assert engine.is_step_complete(JourneyStep.PROPERTY_DETAILS, collected)

    def test_step_incomplete(self, engine):
        collected = {"address": "123 George St"}
        assert not engine.is_step_complete(JourneyStep.PROPERTY_DETAILS, collected)

    # --- Validation Tests ---

    def test_validate_postcode_valid(self, engine):
        valid, error = engine.validate_field("postcode", "4000")
        assert valid is True
        assert error is None

    def test_validate_postcode_invalid(self, engine):
        valid, error = engine.validate_field("postcode", "123")
        assert valid is False

    def test_validate_energy_type_valid(self, engine):
        valid, error = engine.validate_field("energy_type", "electricity")
        assert valid is True

    def test_validate_energy_type_invalid(self, engine):
        valid, error = engine.validate_field("energy_type", "water")
        assert valid is False

    def test_validate_email_valid(self, engine):
        valid, error = engine.validate_field("email", "test@example.com")
        assert valid is True

    def test_validate_email_invalid(self, engine):
        valid, error = engine.validate_field("email", "not-an-email")
        assert valid is False

    def test_validate_required_empty(self, engine):
        valid, error = engine.validate_field("address", "")
        assert valid is False

    def test_validate_unknown_field(self, engine):
        valid, error = engine.validate_field("nonexistent", "value")
        assert valid is False


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 5 — Call State Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCallState:
    """Test the CallState model."""

    def test_from_lead_property_details(self):
        state = CallState.from_lead("ENG-DEMO-001", JourneyStep.PROPERTY_DETAILS)
        assert state.lead_id == "ENG-DEMO-001"
        assert state.current_step == JourneyStep.ENERGY_DETAILS
        assert JourneyStep.PROPERTY_DETAILS in state.completed_steps

    def test_from_lead_energy_details(self):
        state = CallState.from_lead("ENG-DEMO-002", JourneyStep.ENERGY_DETAILS)
        assert state.current_step == JourneyStep.USAGE_DETAILS
        assert JourneyStep.PROPERTY_DETAILS in state.completed_steps
        assert JourneyStep.ENERGY_DETAILS in state.completed_steps

    def test_from_lead_customer_details(self):
        state = CallState.from_lead("ENG-DEMO-004", JourneyStep.CUSTOMER_DETAILS)
        assert state.current_step == JourneyStep.COMPLETION
        assert len(state.completed_steps) == 4

    def test_consent_accepted(self):
        state = CallState(lead_id="TEST")
        state.mark_consent(ConsentStatus.CONSENTED)
        assert state.consent_status == ConsentStatus.CONSENTED
        assert state.call_status == CallStatus.IN_PROGRESS

    def test_consent_declined(self):
        state = CallState(lead_id="TEST")
        state.mark_consent(ConsentStatus.DECLINED)
        assert state.consent_status == ConsentStatus.DECLINED
        assert state.call_status == CallStatus.DECLINED

    def test_save_field(self):
        state = CallState(lead_id="TEST")
        state.save_field("postcode", "4000", confidence=0.98)
        assert state.collected_fields["postcode"] == "4000"
        assert state.confidence == 0.98

    def test_retry_tracking(self):
        state = CallState(lead_id="TEST", max_retries=2)
        state.increment_retry()
        assert state.retry_count == 1
        assert not state.has_exceeded_retries()
        state.increment_retry()
        assert state.has_exceeded_retries()

    def test_advance_step(self):
        state = CallState(lead_id="TEST", current_step=JourneyStep.PROPERTY_DETAILS)
        state.advance_step(JourneyStep.ENERGY_DETAILS)
        assert state.current_step == JourneyStep.ENERGY_DETAILS
        assert JourneyStep.PROPERTY_DETAILS in state.completed_steps

    def test_escalate(self):
        state = CallState(lead_id="TEST")
        state.escalate(EscalationReason.FRUSTRATION, "Customer raised voice")
        assert state.escalation_status == EscalationReason.FRUSTRATION
        assert state.call_status == CallStatus.HANDOFF
        assert state.should_escalate()

    def test_complete_journey(self):
        state = CallState(lead_id="TEST", current_step=JourneyStep.COMPLETION)
        state.completed_steps = list(JOURNEY_STEP_ORDER[:-1])
        state.complete_journey()
        assert state.journey_submission_status.value == "ready"

    def test_add_message(self):
        state = CallState(lead_id="TEST")
        state.add_message("agent", "Hello!")
        state.add_message("customer", "Hi there")
        assert len(state.conversation_history) == 2
        assert state.conversation_history[0].role == "agent"
        assert state.conversation_history[1].content == "Hi there"

    def test_is_active(self):
        state = CallState(lead_id="TEST")
        assert state.is_active()
        state.mark_consent(ConsentStatus.DECLINED)
        assert not state.is_active()

    def test_dnc_check(self):
        state = CallState(lead_id="TEST")
        state.mark_dnc_checked(allowed=True)
        assert state.dnc_checked
        assert state.dnc_allowed
