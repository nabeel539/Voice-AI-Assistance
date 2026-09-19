"""
CIMET Reconnect — Speech-to-Text (STT) Service

Decoupled interface and OpenAI Whisper implementation for transcribing customer audio.
"""

from abc import ABC, abstractmethod
import io
from pathlib import Path
from typing import BinaryIO, Optional, Union
from openai import OpenAI
from pydantic import BaseModel

from app.config import get_settings


class TranscriptionResult(BaseModel):
    """Result of speech-to-text processing."""
    text: str
    confidence: float = 1.0
    language: str = "en"
    duration_seconds: Optional[float] = None


class SpeechToTextService(ABC):
    """Abstract interface for speech-to-text providers."""

    @abstractmethod
    def transcribe(self, audio_data: Union[bytes, BinaryIO, Path, str]) -> TranscriptionResult:
        """Transcribe audio into text."""
        ...


class OpenAISTTService(SpeechToTextService):
    """OpenAI Whisper STT implementation."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        settings = get_settings()
        self._api_key = api_key or settings.openai_api_key
        self._model = model or settings.openai_stt_model or "whisper-1"
        self._client: Optional[OpenAI] = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def transcribe(self, audio_data: Union[bytes, BinaryIO, Path, str]) -> TranscriptionResult:
        client = self._get_client()

        if isinstance(audio_data, bytes):
            # Wrap bytes in a named buffer for the OpenAI client
            file_obj = io.BytesIO(audio_data)
            file_obj.name = "audio.wav"
            resp = client.audio.transcriptions.create(
                model=self._model,
                file=file_obj,
                response_format="verbose_json",
            )
        elif isinstance(audio_data, (str, Path)):
            with open(str(audio_data), "rb") as f:
                resp = client.audio.transcriptions.create(
                    model=self._model,
                    file=f,
                    response_format="verbose_json",
                )
        else:
            resp = client.audio.transcriptions.create(
                model=self._model,
                file=audio_data,
                response_format="verbose_json",
            )

        text = getattr(resp, "text", str(resp)).strip()
        duration = getattr(resp, "duration", None)

        return TranscriptionResult(
            text=text,
            confidence=0.95 if text else 0.0,
            duration_seconds=duration,
        )


class MockSTTService(SpeechToTextService):
    """Mock STT service for testing without incurring API costs."""

    def __init__(self, mock_transcript: str = "Yes, my postcode is 3000"):
        self.mock_transcript = mock_transcript

    def transcribe(self, audio_data: Union[bytes, BinaryIO, Path, str]) -> TranscriptionResult:
        return TranscriptionResult(
            text=self.mock_transcript,
            confidence=0.98,
            duration_seconds=2.5,
        )
