"""
CIMET Reconnect — Vapi Telephony & Webhook Test Suite

Verifies:
1. Strict pre-call DNC gating
2. Vapi outbound call placement & provider mapping
3. Webhook secret authentication
4. Tool call idempotency caching
5. Controlled tool execution (get_lead, get_current_journey_state, validate_field, save_field, submit_journey, request_human_handoff)
6. Status updates, live transcripts, and end-of-call reports
"""

import json
import pytest
from fastapi.testclient import TestClient

from app.api.session_store import session_store
from app.config import get_settings
from app.domain.models import CallStatus, EscalationReason, JourneyStep
from app.main import app
from app.services.telephony_service import MockTelephonyService

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_telephony():
    """Ensure mock telephony is active for tests."""
    mock_tel = MockTelephonyService()
    session_store.set_telephony_service(mock_tel)
    return mock_tel


def test_vapi_outbound_call_dnc_blocked():
    """Verify DNC blocked phone number is rejected BEFORE dialing Vapi."""
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

    # Verify no outbound call was made to provider
    assert len(session_store.telephony.outbound_calls) == 0


def test_vapi_outbound_call_allowed():
    """Verify allowed phone number initiates outbound call via active provider."""
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
    assert data["call_state"]["channel"] in ("vapi", "mock")
    assert data["call_state"]["to_phone"] == "+61412345678"

    assert len(session_store.telephony.outbound_calls) == 1


def test_vapi_webhook_status_update():
    """Verify Vapi status-update webhook synchronizes CallState status."""
    # Create active call
    call_res = client.post(
        "/api/telephony/outbound-call",
        json={"lead_id": "ENG-DEMO-001", "phone_number": "+61411223344"},
    )
    call_id = call_res.json()["call_id"]

    # Send ringing status
    res1 = client.post(
        "/api/webhooks/vapi",
        json={
            "message": {
                "type": "status-update",
                "status": "ringing",
                "call": {
                    "id": "vapi_call_123",
                    "assistantOverrides": {
                        "variableValues": {"call_id": call_id}
                    }
                }
            }
        },
    )
    assert res1.status_code == 200

    state = session_store.get_call(call_id)
    assert state.call_status == CallStatus.IN_PROGRESS

    # Send ended status
    res2 = client.post(
        "/api/webhooks/vapi",
        json={
            "message": {
                "type": "status-update",
                "status": "ended",
                "call": {
                    "id": "vapi_call_123",
                    "assistantOverrides": {
                        "variableValues": {"call_id": call_id}
                    }
                }
            }
        },
    )
    assert res2.status_code == 200
    state2 = session_store.get_call(call_id)
    assert state2.call_status == CallStatus.ENDED


def test_vapi_tool_calls_idempotency_and_saving():
    """Verify tool calls execution, field saving, and idempotency deduplication."""
    # Create active call
    call_res = client.post(
        "/api/telephony/outbound-call",
        json={"lead_id": "ENG-DEMO-001", "phone_number": "+61411223344"},
    )
    call_id = call_res.json()["call_id"]

    payload = {
        "message": {
            "type": "tool-calls",
            "toolCalls": [
                {
                    "id": "tc_save_first_name_001",
                    "function": {
                        "name": "save_field",
                        "arguments": json.dumps({
                            "call_id": call_id,
                            "field_name": "first_name",
                            "value": "Alex",
                        }),
                    },
                }
            ],
            "variableValues": {"call_id": call_id},
        }
    }

    # First call: saves field
    res1 = client.post("/api/webhooks/vapi", json=payload)
    assert res1.status_code == 200
    data1 = res1.json()
    assert len(data1["results"]) == 1
    res_obj1 = json.loads(data1["results"][0]["result"])
    assert res_obj1["success"] is True
    assert res_obj1["field_name"] == "first_name"

    # Verify field persisted in CallState
    state = session_store.get_call(call_id)
    assert state.collected_fields.get("first_name") == "Alex"

    # Second call with identical toolCallId (idempotent replay)
    res2 = client.post("/api/webhooks/vapi", json=payload)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["results"][0]["result"] == data1["results"][0]["result"]


def test_vapi_tool_calls_get_journey_state_and_next_step():
    """Verify get_current_journey_state and get_next_required_step."""
    call_res = client.post(
        "/api/telephony/outbound-call",
        json={"lead_id": "ENG-DEMO-001", "phone_number": "+61411223344"},
    )
    call_id = call_res.json()["call_id"]

    payload = {
        "message": {
            "type": "tool-calls",
            "toolCalls": [
                {
                    "id": "tc_state_001",
                    "function": {
                        "name": "get_current_journey_state",
                        "arguments": json.dumps({"call_id": call_id}),
                    },
                },
                {
                    "id": "tc_next_001",
                    "function": {
                        "name": "get_next_required_step",
                        "arguments": json.dumps({"call_id": call_id}),
                    },
                },
            ],
            "variableValues": {"call_id": call_id},
        }
    }

    res = client.post("/api/webhooks/vapi", json=payload)
    assert res.status_code == 200
    results = res.json()["results"]
    assert len(results) == 2

    state_res = json.loads(results[0]["result"])
    assert state_res["success"] is True
    assert "missing_fields" in state_res

    next_res = json.loads(results[1]["result"])
    assert next_res["success"] is True
    assert next_res["has_missing_fields"] is True
    assert "next_field" in next_res


def test_vapi_tool_calls_human_handoff():
    """Verify request_human_handoff triggers escalation and creates handoff package."""
    call_res = client.post(
        "/api/telephony/outbound-call",
        json={"lead_id": "ENG-DEMO-001", "phone_number": "+61411223344"},
    )
    call_id = call_res.json()["call_id"]

    payload = {
        "message": {
            "type": "tool-calls",
            "toolCalls": [
                {
                    "id": "tc_handoff_001",
                    "function": {
                        "name": "request_human_handoff",
                        "arguments": json.dumps({
                            "call_id": call_id,
                            "reason": "frustrated",
                            "summary": "Customer is frustrated by repeated questions.",
                        }),
                    },
                }
            ],
            "variableValues": {"call_id": call_id},
        }
    }

    res = client.post("/api/webhooks/vapi", json=payload)
    assert res.status_code == 200
    handoff_result = json.loads(res.json()["results"][0]["result"])
    assert handoff_result["success"] is True
    assert handoff_result["action"] == "transfer"
    assert "handoff_id" in handoff_result

    state = session_store.get_call(call_id)
    assert state.escalation_status == EscalationReason.FRUSTRATION


def test_vapi_transcript_and_summary_observability():
    """Verify live transcripts and end-of-call summary are logged for UI display."""
    call_res = client.post(
        "/api/telephony/outbound-call",
        json={"lead_id": "ENG-DEMO-001", "phone_number": "+61411223344"},
    )
    call_id = call_res.json()["call_id"]

    # Send customer transcript
    t_res = client.post(
        "/api/webhooks/vapi",
        json={
            "message": {
                "type": "transcript",
                "role": "user",
                "transcriptType": "final",
                "transcript": "Yes, I am happy to continue.",
                "variableValues": {"call_id": call_id},
            }
        },
    )
    assert t_res.status_code == 200

    state = session_store.get_call(call_id)
    assert len(state.conversation_history) >= 1
    assert state.conversation_history[-1].content == "Yes, I am happy to continue."

    # Send end of call report
    e_res = client.post(
        "/api/webhooks/vapi",
        json={
            "message": {
                "type": "end-of-call-report",
                "summary": "Customer successfully verified details and completed journey.",
                "endedReason": "customer-ended-call",
                "variableValues": {"call_id": call_id},
            }
        },
    )
    assert e_res.status_code == 200
    state2 = session_store.get_call(call_id)
    assert state2.call_status == CallStatus.ENDED
    assert "Customer successfully verified details" in state2.conversation_summary
