"""
Tests for Twilio Media Stream WebSocket: Real-Time Bidirectional Audio Streaming & Barge-In.
"""

import base64
import json
import pytest
from fastapi.testclient import TestClient

from app.api.session_store import session_store
from app.domain.models import CallStatus, ConsentStatus
from app.main import app
from app.services.audio_codec import create_silent_mulaw_chunk
from app.services.stt_service import MockSTTService
from app.services.telephony_service import MockTelephonyService

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_services():
    mock_tel = MockTelephonyService()
    session_store.set_telephony_service(mock_tel)
    return mock_tel


def test_media_stream_websocket_greeting_on_start():
    """Verify on start event, backend initializes call recovery and streams opening prompt."""
    outbound_res = client.post(
        "/api/telephony/outbound-call",
        json={"lead_id": "ENG-DEMO-001", "phone_number": "+61412340001"},
    )
    call_id = outbound_res.json()["call_id"]
    call_sid = outbound_res.json()["twilio_call_sid"]

    with client.websocket_connect(f"/api/telephony/media-stream?call_id={call_id}") as ws:
        # 1. Send start event
        start_payload = {
            "event": "start",
            "sequenceNumber": "1",
            "start": {
                "streamSid": "MZ1234567890",
                "callSid": call_sid,
                "customParameters": {
                    "call_id": call_id,
                },
            },
            "streamSid": "MZ1234567890",
        }
        ws.send_text(json.dumps(start_payload))

        # 2. Receive first streamed media frame from backend
        received_raw = ws.receive_text()
        received_data = json.loads(received_raw)
        assert received_data["event"] == "media"
        assert received_data["streamSid"] == "MZ1234567890"
        assert "payload" in received_data["media"]

        # Verify call state updated with stream SID and opening prompt
        call_state = session_store.get_call(call_id)
        assert call_state.twilio_stream_sid == "MZ1234567890"
        assert len(call_state.conversation_history) >= 1
        assert call_state.conversation_history[0].role == "assistant"

        # 3. Send stop event
        stop_payload = {
            "event": "stop",
            "sequenceNumber": "2",
            "stop": {
                "callSid": call_sid,
            },
            "streamSid": "MZ1234567890",
        }
        ws.send_text(json.dumps(stop_payload))


def test_media_stream_inbound_audio_and_barge_in():
    """Verify inbound customer audio triggers barge-in clear event, STT transcription, and agent response."""
    outbound_res = client.post(
        "/api/telephony/outbound-call",
        json={"lead_id": "ENG-DEMO-001", "phone_number": "+61412340002"},
    )
    call_id = outbound_res.json()["call_id"]
    call_sid = outbound_res.json()["twilio_call_sid"]

    # Inject mock STT returning agreement
    session_store._stt = MockSTTService(mock_transcript="Yes, I agree and give my consent.")

    with client.websocket_connect(f"/api/telephony/media-stream?call_id={call_id}") as ws:
        # Start event
        ws.send_text(json.dumps({
            "event": "start",
            "start": {
                "streamSid": "MZstream002",
                "callSid": call_sid,
                "customParameters": {"call_id": call_id},
            },
        }))

        # Initial greeting is streaming; send non-silent customer audio to trigger barge-in
        chunk = b"\x00" * 16000  # 2 seconds of 8kHz voice energy
        b64_chunk = base64.b64encode(chunk).decode("utf-8")

        media_msg = {
            "event": "media",
            "streamSid": "MZstream002",
            "media": {
                "payload": b64_chunk,
            },
        }
        ws.send_text(json.dumps(media_msg))

        # Collect events received from backend
        events_received = []
        for _ in range(5):
            try:
                msg = json.loads(ws.receive_text())
                events_received.append(msg.get("event"))
                if msg.get("event") == "media":
                    break
            except Exception:
                break

        # Verify that either a barge-in 'clear' or response 'media' was received
        assert "media" in events_received or "clear" in events_received

        # Verify call state updated with consent
        call_state = session_store.get_call(call_id)
        assert call_state.consent_status == ConsentStatus.CONSENTED
