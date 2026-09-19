"""
CIMET Reconnect — API Integration Tests

Tests for all Phase 10 REST endpoints:
- Leads: GET /api/leads, GET /api/leads/{id}, POST /api/leads/{id}/start-call
- Calls: GET /api/calls, GET /api/calls/{id}/state, POST /api/calls/{id}/end, GET /api/calls/handoffs
- Voice: POST /api/voice/process-turn-json, POST /api/voice/process-turn
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.api.session_store import session_store
from app.domain.models import CallStatus, EscalationReason


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestLeadsAPI:
    def test_list_leads(self, client):
        resp = client.get("/api/leads")
        assert resp.status_code == 200
        leads = resp.json()
        assert isinstance(leads, list)
        assert len(leads) >= 4
        assert any(l["lead_id"] == "ENG-DEMO-001" for l in leads)

    def test_get_lead_success(self, client):
        resp = client.get("/api/leads/ENG-DEMO-001")
        assert resp.status_code == 200
        lead = resp.json()
        assert lead["lead_id"] == "ENG-DEMO-001"
        assert lead["last_completed_step"] == "property_details"

    def test_get_lead_not_found(self, client):
        resp = client.get("/api/leads/UNKNOWN-999")
        assert resp.status_code == 404

    def test_start_call_success(self, client):
        resp = client.post("/api/leads/ENG-DEMO-001/start-call?generate_voice=false")
        assert resp.status_code == 200
        data = resp.json()
        assert "call_id" in data
        assert data["lead_id"] == "ENG-DEMO-001"
        assert data["status"] == "active"
        assert "recorded" in data["agent_message"].lower()

    def test_start_call_dnc_blocked(self, client):
        from app.api.session_store import session_store
        lead = session_store.dataset_adapter.get_lead("ENG-DEMO-001")
        target_phone = lead.phone or lead.test_contact or "+61400000001"
        session_store.toolbox.dnc_service.block_number(target_phone)
        try:
            resp = client.post("/api/leads/ENG-DEMO-001/start-call?generate_voice=false")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "dnc_blocked"
            assert data["call_state"]["call_status"] == CallStatus.DECLINED
            assert data["call_state"]["dnc_allowed"] is False
            assert "Do-Not-Call" in data["agent_message"]
            # Verify blocked call was NOT persisted into active calls
        finally:
            session_store.toolbox.dnc_service.unblock_number(target_phone)
            session_store.toolbox.dnc_service.unblock_number("+61400000001")




class TestCallsAPI:
    def test_get_call_state(self, client):
        # Start a call first
        start_resp = client.post("/api/leads/ENG-DEMO-002/start-call?generate_voice=false")
        call_id = start_resp.json()["call_id"]

        resp = client.get(f"/api/calls/{call_id}/state")
        assert resp.status_code == 200
        state = resp.json()
        assert state["call_id"] == call_id
        assert state["lead_id"] == "ENG-DEMO-002"

    def test_end_call(self, client):
        start_resp = client.post("/api/leads/ENG-DEMO-003/start-call?generate_voice=false")
        call_id = start_resp.json()["call_id"]

        resp = client.post(f"/api/calls/{call_id}/end")
        assert resp.status_code == 200
        assert resp.json()["call_status"] == CallStatus.ENDED


class TestVoiceRecoveryTurnAPI:
    def test_interactive_consent_and_collection_loop(self, client):
        # 1. Start recovery call for lead ENG-DEMO-003 (missing customer_details: first_name, last_name, email)
        start_resp = client.post("/api/leads/ENG-DEMO-003/start-call?generate_voice=false")
        call_id = start_resp.json()["call_id"]

        # 2. Customer provides consent
        turn1 = client.post(
            "/api/voice/process-turn-json",
            json={"call_id": call_id, "text": "Yes, that is fine, please continue", "generate_voice": False},
        )
        assert turn1.status_code == 200
        data1 = turn1.json()
        assert data1["status"] == "active"
        assert data1["call_state"]["consent_status"] == "consented"
        assert "first" in data1["agent_message"].lower() or "name" in data1["agent_message"].lower()

        # 3. Customer answers first name
        turn2 = client.post(
            "/api/voice/process-turn-json",
            json={"call_id": call_id, "text": "My first name is Sarah", "generate_voice": False},
        )
        assert turn2.status_code == 200
        data2 = turn2.json()
        assert data2["call_state"]["collected_fields"]["first_name"] == "Sarah"

    def test_voice_turn_guardrail_triggers_handoff(self, client):
        start_resp = client.post("/api/leads/ENG-DEMO-001/start-call?generate_voice=false")
        call_id = start_resp.json()["call_id"]

        # Customer mentions credit card details during call
        turn = client.post(
            "/api/voice/process-turn-json",
            json={"call_id": call_id, "text": "Can I pay with my visa card 4532 1234 5678 9010", "generate_voice": False},
        )
        assert turn.status_code == 200
        data = turn.json()
        assert data["status"] == "handed_off"
        assert data["handoff_package"] is not None
        assert data["handoff_package"]["escalation_reason"] == EscalationReason.PAYMENT

        # Check operator handoff list
        handoffs_resp = client.get("/api/calls/handoffs")
        assert handoffs_resp.status_code == 200
        handoffs = handoffs_resp.json()
        assert len(handoffs) >= 1
        assert any(h["escalation_reason"] == "payment" for h in handoffs)
