"""
Tests for Twilio Telephony Endpoints, DNC Pre-Call Gating, TwiML Generation, and Call State Tracking.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.session_store import session_store
from app.domain.models import CallStatus, JourneyStep
from app.main import app
from app.services.telephony_service import MockTelephonyService

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_mock_telephony():
    """Ensure mock telephony is active for tests."""
    mock_tel = MockTelephonyService()
    session_store.set_telephony_service(mock_tel)
    return mock_tel


def test_outbound_call_dnc_blocked():
    """Verify DNC blocked phone number is rejected BEFORE dialing Twilio."""
    # Suffix 999 is blocked in MockDNCService
    response = client.post(
        "/api/telephony/outbound-call",
        json={"lead_id": "ENG-DEMO-001", "phone_number": "+61400000999"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "dnc_blocked"
    assert data["twilio_call_sid"] is None
    assert data["call_state"]["dnc_checked"] is True
    assert data["call_state"]["dnc_allowed"] is False
    assert data["call_state"]["call_status"] == "declined"

    # Verify no outbound call was made
    assert len(session_store.telephony.outbound_calls) == 0


def test_outbound_call_allowed():
    """Verify allowed phone number triggers outbound Twilio call."""
    response = client.post(
        "/api/telephony/outbound-call",
        json={"lead_id": "ENG-DEMO-001", "phone_number": "+61412345678"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "initiated"
    assert data["twilio_call_sid"] is not None
    assert data["call_state"]["dnc_checked"] is True
    assert data["call_state"]["dnc_allowed"] is True
    assert data["call_state"]["channel"] in ("vapi", "twilio", "mock")
    assert data["call_state"]["to_phone"] == "+61412345678"

    # Verify call is recorded in telephony service
    assert len(session_store.telephony.outbound_calls) == 1
    recorded = session_store.telephony.outbound_calls[0]
    assert recorded["to_number"] == "+61412345678"
    assert recorded["lead_id"] == "ENG-DEMO-001"


def test_voice_webhook_twiml_generation():
    """Verify Twilio voice webhook generates valid TwiML connecting to media stream."""
    # First create a call
    outbound_res = client.post(
        "/api/telephony/outbound-call",
        json={"lead_id": "ENG-DEMO-002", "phone_number": "+61488888888"},
    )
    call_id = outbound_res.json()["call_id"]
    call_sid = outbound_res.json()["twilio_call_sid"]

    # When Twilio calls the webhook on answer
    webhook_res = client.post(
        f"/api/telephony/voice-webhook?call_id={call_id}",
        data={"CallSid": call_sid, "From": "+61488888888", "CallStatus": "in-progress"},
    )
    assert webhook_res.status_code == 200
    assert "application/xml" in webhook_res.headers["content-type"]
    xml_content = webhook_res.text
    assert "<Response>" in xml_content
    assert "<Connect>" in xml_content
    assert "<Stream" in xml_content
    assert "/api/telephony/media-stream" in xml_content


def test_status_callback_updates_call_state():
    """Verify Twilio status callback transitions call status."""
    outbound_res = client.post(
        "/api/telephony/outbound-call",
        json={"lead_id": "ENG-DEMO-003", "phone_number": "+61455555555"},
    )
    call_id = outbound_res.json()["call_id"]
    call_sid = outbound_res.json()["twilio_call_sid"]

    # Status answered -> in-progress
    client.post(
        "/api/telephony/status-callback",
        data={"CallSid": call_sid, "CallStatus": "in-progress"},
    )
    state = session_store.get_call(call_id)
    assert state.call_status == CallStatus.IN_PROGRESS

    # Status completed -> ended
    client.post(
        "/api/telephony/status-callback",
        data={"CallSid": call_sid, "CallStatus": "completed"},
    )
    assert state.call_status == CallStatus.ENDED


def test_call_sid_lookup_in_session_store():
    """Verify looking up call by Twilio Call SID."""
    outbound_res = client.post(
        "/api/telephony/outbound-call",
        json={"lead_id": "ENG-DEMO-004", "phone_number": "+61477777777"},
    )
    call_id = outbound_res.json()["call_id"]
    call_sid = outbound_res.json()["twilio_call_sid"]

    looked_up = session_store.get_call_by_twilio_sid(call_sid)
    assert looked_up is not None
    assert looked_up.call_id == call_id
    assert looked_up.lead_id == "ENG-DEMO-004"


def test_simulate_phone_turn_journey_progression():
    """Verify simulate-phone-turn runs through shared LangGraph agent and returns mu-law audio."""
    outbound_res = client.post(
        "/api/telephony/outbound-call",
        json={"lead_id": "ENG-DEMO-001", "phone_number": "+61411112222"},
    )
    call_id = outbound_res.json()["call_id"]

    # Turn 1: Customer gives recording consent
    turn1 = client.post(
        "/api/telephony/simulate-phone-turn",
        json={"call_id": call_id, "customer_speech_text": "Yes, that's fine, I agree."},
    )
    assert turn1.status_code == 200
    d1 = turn1.json()
    assert d1["call_state"]["consent_status"] == "consented"
    assert d1["mulaw_base64"] is not None
    assert len(d1["mulaw_base64"]) > 0

    # Turn 2: Customer provides missing field (postcode 2000)
    turn2 = client.post(
        "/api/telephony/simulate-phone-turn",
        json={"call_id": call_id, "customer_speech_text": "My postcode is 2000 in Sydney."},
    )
    assert turn2.status_code == 200
    d2 = turn2.json()
    assert d2["call_state"]["collected_fields"].get("postcode") == "2000"


def test_simulate_phone_turn_frustration_escalation():
    """Verify frustration on phone triggers warm handoff package."""
    outbound_res = client.post(
        "/api/telephony/outbound-call",
        json={"lead_id": "ENG-DEMO-001", "phone_number": "+61411113333"},
    )
    call_id = outbound_res.json()["call_id"]

    # Customer expresses frustration
    res = client.post(
        "/api/telephony/simulate-phone-turn",
        json={"call_id": call_id, "customer_speech_text": "This is ridiculous and I am getting very frustrated!"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "handed_off"
    assert data["call_state"]["call_status"] == "handoff"
    assert data["call_state"]["escalation_status"] == "frustration"
    assert data["handoff_package"] is not None
    assert data["handoff_package"]["escalation_reason"] == "frustration"
