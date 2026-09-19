"""
CIMET Reconnect — Telephony Service

Provider-agnostic telephony abstraction supporting Vapi (active), Twilio (legacy/preserved),
and Mock Telephony (testing/offline).
"""

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, List, Optional
import urllib.parse
from uuid import uuid4
import requests

from app.config import get_settings

logger = logging.getLogger("cimet.telephony")


class TelephonyService(ABC):
    """Abstract interface for telephony providers."""

    @abstractmethod
    def place_outbound_call(
        self,
        to_number: str,
        lead_id: str,
        call_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Initiate an outbound phone call and return the provider Call ID / SID."""
        ...

    @abstractmethod
    def end_call(self, provider_call_id: str) -> bool:
        """Terminate an active phone call."""
        ...

    @abstractmethod
    def validate_webhook(
        self,
        headers: Dict[str, str],
        body: bytes,
    ) -> bool:
        """Validate an incoming webhook request from the telephony provider."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return provider identifier (e.g. 'vapi', 'twilio', 'mock')."""
        ...


# ─── Vapi Telephony Provider (Active) ─────────────────────────────────────────

class VapiService(TelephonyService):
    """
    Production Vapi Voice Provider.
    Initiates calls via Vapi REST API (POST https://api.vapi.ai/call) and routes
    STT/LLM/TTS tool calls back to CIMET FastAPI webhooks.
    """

    BASE_URL = "https://api.vapi.ai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        assistant_id: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        server_url: Optional[str] = None,
        webhook_secret: Optional[str] = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.vapi_api_key
        self.assistant_id = assistant_id or settings.vapi_assistant_id
        self.phone_number_id = phone_number_id or settings.vapi_phone_number_id
        self.server_url = (server_url or settings.vapi_server_url).rstrip("/")
        self.webhook_secret = webhook_secret or settings.vapi_webhook_secret

    @property
    def provider_name(self) -> str:
        return "vapi"

    def place_outbound_call(
        self,
        to_number: str,
        lead_id: str,
        call_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create an outbound call via Vapi API (POST /call).
        Raises explicit error if credentials are unconfigured (no silent mock fallback in live mode).
        """
        if not self.api_key:
            raise ValueError(
                "Vapi API Key (VAPI_API_KEY) is not configured. Please set it in your environment."
            )
        if not self.phone_number_id:
            raise ValueError(
                "Vapi Phone Number ID (VAPI_PHONE_NUMBER_ID) is not configured. Outbound calls require a registered Vapi phone number ID."
            )
        if not self.assistant_id:
            raise ValueError(
                "Vapi Assistant ID (VAPI_ASSISTANT_ID) is not configured. Please set it in your environment."
            )

        endpoint = f"{self.BASE_URL}/call"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Construct minimal context payload (zero unnecessary customer PII)
        variable_values = {
            "call_id": call_id,
            "lead_id": lead_id,
        }
        if context:
            for k, v in context.items():
                if k in ("last_completed_step", "energy_type"):
                    variable_values[k] = str(v)

        webhook_url = f"{self.server_url}/api/webhooks/vapi" if self.server_url else None

        payload: Dict[str, Any] = {
            "phoneNumberId": self.phone_number_id,
            "assistantId": self.assistant_id,
            "customer": {
                "number": to_number,
            },
            "assistantOverrides": {
                "variableValues": variable_values,
            },
        }

        if webhook_url:
            payload["assistantOverrides"]["serverUrl"] = webhook_url
        if self.webhook_secret:
            payload["assistantOverrides"]["serverUrlSecret"] = self.webhook_secret

        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=15)
            if not response.ok:
                error_body = response.text
                logger.error(f"[VAPI_CALL_FAILED] HTTP {response.status_code}: {error_body}")
                raise RuntimeError(
                    f"Vapi API returned error {response.status_code}: {error_body}"
                )
            data = response.json()
            vapi_call_id = data.get("id")
            if not vapi_call_id:
                raise RuntimeError(f"Vapi response missing call 'id': {data}")
            return vapi_call_id
        except requests.RequestException as e:
            logger.error(f"[VAPI_NETWORK_ERROR] Failed to contact Vapi API: {e}")
            raise RuntimeError(f"Network error connecting to Vapi API: {e}") from e

    def end_call(self, provider_call_id: str) -> bool:
        """End an active Vapi call."""
        if not self.api_key:
            return False
        endpoint = f"{self.BASE_URL}/call/{provider_call_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        try:
            res = requests.delete(endpoint, headers=headers, timeout=10)
            return res.ok
        except Exception as e:
            logger.warning(f"[VAPI_END_CALL_ERROR] Failed ending call {provider_call_id}: {e}")
            return False

    def validate_webhook(
        self,
        headers: Dict[str, str],
        body: bytes,
    ) -> bool:
        """Validate incoming Vapi webhook request using secret header."""
        settings = get_settings()
        if settings.app_env != "production" and not self.webhook_secret:
            return True
        if not self.webhook_secret:
            return True
        incoming_secret = (
            headers.get("x-vapi-secret")
            or headers.get("X-Vapi-Secret")
            or headers.get("x-vapi-signature")
        )
        return incoming_secret == self.webhook_secret


# ─── Legacy Twilio Telephony Provider (Preserved / Inactive) ──────────────────

class TwilioService(TelephonyService):
    """
    Legacy Twilio Telephony implementation.
    Preserved for rollback and reference. Inactive during standard Vapi operation.
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        phone_number: Optional[str] = None,
        webhook_base_url: Optional[str] = None,
    ):
        settings = get_settings()
        self.account_sid = account_sid or settings.effective_twilio_account_sid
        self.auth_token = auth_token or settings.effective_twilio_auth_token
        self.phone_number = phone_number or settings.effective_twilio_phone_number
        self.webhook_base_url = (webhook_base_url or settings.twilio_webhook_base_url).rstrip("/")
        self._client: Optional[Any] = None

    @property
    def provider_name(self) -> str:
        return "twilio"

    def _get_client(self) -> Any:
        if self._client is None:
            settings = get_settings()
            api_key = settings.twilio_api_key_sid
            api_secret = settings.twilio_api_key_secret

            from twilio.rest import Client as TwilioClient
            if api_key and api_secret:
                self._client = TwilioClient(api_key, api_secret, account_sid=self.account_sid)
            elif self.account_sid and self.auth_token:
                self._client = TwilioClient(self.account_sid, self.auth_token)
            else:
                raise ValueError(
                    "Twilio credentials (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) are not configured."
                )
        return self._client

    def place_outbound_call(
        self,
        to_number: str,
        lead_id: str,
        call_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        client = self._get_client()
        base_url = self.webhook_base_url
        if not base_url:
            raise ValueError("Twilio webhook base URL is required (TWILIO_WEBHOOK_BASE_URL).")

        webhook_url = f"{base_url}/api/telephony/voice-webhook?call_id={urllib.parse.quote(call_id)}"
        status_url = f"{base_url}/api/telephony/status-callback?call_id={urllib.parse.quote(call_id)}"

        call = client.calls.create(
            to=to_number,
            from_=self.phone_number,
            url=webhook_url,
            status_callback=status_url,
        )
        return call.sid

    def end_call(self, provider_call_id: str) -> bool:
        try:
            client = self._get_client()
            client.calls(provider_call_id).update(status="completed")
            return True
        except Exception:
            return False

    def validate_webhook(
        self,
        headers: Dict[str, str],
        body: bytes,
    ) -> bool:
        return True

    def generate_media_stream_twiml(
        self,
        call_id: str,
        stream_ws_url: str,
        custom_params: Optional[Dict[str, str]] = None,
    ) -> str:
        from twilio.twiml.voice_response import Connect, Stream, VoiceResponse
        response = VoiceResponse()
        connect = Connect()
        stream = Stream(url=stream_ws_url)
        stream.parameter(name="call_id", value=call_id)
        if custom_params:
            for k, v in custom_params.items():
                stream.parameter(name=k, value=str(v))
        connect.append(stream)
        response.append(connect)
        return str(response)

    def generate_farewell_twiml(self, message: str = "Thank you. Goodbye!") -> str:
        from twilio.twiml.voice_response import VoiceResponse
        response = VoiceResponse()
        response.say(message, voice="Polly.Nicole", language="en-AU")
        response.hangup()
        return str(response)


# ─── Mock Telephony Provider (Testing & Offline Development) ──────────────────

class MockTelephonyService(TelephonyService):
    """Mock telephony service for fast local unit testing and offline development."""

    def __init__(self):
        self.outbound_calls: List[Dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return "mock"

    def place_outbound_call(
        self,
        to_number: str,
        lead_id: str,
        call_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        call_sid = f"vapi_{uuid4().hex[:24]}"
        self.outbound_calls.append({
            "call_sid": call_sid,
            "to_number": to_number,
            "lead_id": lead_id,
            "call_id": call_id,
            "context": context or {},
        })
        return call_sid

    def end_call(self, provider_call_id: str) -> bool:
        return True

    def validate_webhook(
        self,
        headers: Dict[str, str],
        body: bytes,
    ) -> bool:
        return True

    def generate_media_stream_twiml(
        self,
        call_id: str,
        stream_ws_url: str,
        custom_params: Optional[Dict[str, str]] = None,
    ) -> str:
        return f"<Response><Connect><Stream url='{stream_ws_url}'/></Connect></Response>"

    def generate_farewell_twiml(self, message: str = "Thank you. Goodbye!") -> str:
        return f"<Response><Say>{message}</Say><Hangup/></Response>"
