"""
CIMET Reconnect — Active Call Session Store

Manages active call instances and dependencies across API endpoints.
"""

from typing import Dict, Optional
from app.agent.graph import EnergyRecoveryAgent
from app.agent.tools import AgentToolbox
from app.domain.call_state import CallState
from app.config import get_settings
from app.services.dataset_adapter import DatasetAdapter, MockDatasetAdapter
from app.services.stt_service import OpenAISTTService, SpeechToTextService
from app.services.telephony_service import MockTelephonyService, TelephonyService, TwilioService
from app.services.tts_service import OpenAITTSService, TextToSpeechService


class CallSessionStore:
    """In-memory store for active calls and singleton recovery services."""

    def __init__(self):
        self._active_calls: Dict[str, CallState] = {}
        self._twilio_sid_to_call_id: Dict[str, str] = {}
        self._dataset_adapter: DatasetAdapter = MockDatasetAdapter()
        self._toolbox = AgentToolbox()
        self._agent = EnergyRecoveryAgent(self._toolbox)
        self._stt: Optional[SpeechToTextService] = None
        self._tts: Optional[TextToSpeechService] = None
        self._telephony: Optional[TelephonyService] = None

    @property
    def dataset_adapter(self) -> DatasetAdapter:
        return self._dataset_adapter

    @property
    def agent(self) -> EnergyRecoveryAgent:
        return self._agent

    @property
    def toolbox(self) -> AgentToolbox:
        return self._toolbox

    @property
    def stt(self) -> SpeechToTextService:
        if self._stt is None:
            self._stt = OpenAISTTService()
        return self._stt

    @property
    def tts(self) -> TextToSpeechService:
        if self._tts is None:
            self._tts = OpenAITTSService()
        return self._tts

    @property
    def telephony(self) -> TelephonyService:
        if self._telephony is None:
            settings = get_settings()
            if settings.telephony_simulate:
                self._telephony = MockTelephonyService()
            elif settings.telephony_provider == "vapi":
                from app.services.telephony_service import VapiService
                self._telephony = VapiService()
            elif settings.telephony_provider == "twilio":
                from app.services.telephony_service import TwilioService
                self._telephony = TwilioService()
            else:
                self._telephony = MockTelephonyService()
        return self._telephony

    def set_telephony_service(self, service: TelephonyService) -> None:
        """Allow injecting mock telephony service for tests."""
        self._telephony = service

    def save_call(self, call_state: CallState) -> None:
        self._active_calls[call_state.call_id] = call_state
        if call_state.twilio_call_sid:
            self._twilio_sid_to_call_id[call_state.twilio_call_sid] = call_state.call_id

    def map_twilio_call(self, twilio_call_sid: str, call_id: str) -> None:
        self._twilio_sid_to_call_id[twilio_call_sid] = call_id

    def get_call(self, call_id: str) -> Optional[CallState]:
        return self._active_calls.get(call_id)

    def get_call_by_twilio_sid(self, twilio_call_sid: str) -> Optional[CallState]:
        call_id = self._twilio_sid_to_call_id.get(twilio_call_sid)
        if call_id:
            return self.get_call(call_id)
        # Search direct attribute match as fallback
        for c in self._active_calls.values():
            if c.twilio_call_sid == twilio_call_sid:
                return c
        return None

    def remove_call(self, call_id: str) -> Optional[CallState]:
        call = self._active_calls.pop(call_id, None)
        if call and call.twilio_call_sid:
            self._twilio_sid_to_call_id.pop(call.twilio_call_sid, None)
        return call

    def list_calls(self) -> list[CallState]:
        return list(self._active_calls.values())


# Global singleton instance for application lifespan
session_store = CallSessionStore()
