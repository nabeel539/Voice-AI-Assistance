"""
CIMET Reconnect — Text-to-Speech (TTS) Service

Decoupled interface and OpenAI implementation for synthesizing agent responses into voice audio.
Supports custom voice persona instructions as validated in Phase 0.
"""

from abc import ABC, abstractmethod
import io
from pathlib import Path
from typing import Optional, Union
from openai import OpenAI

from app.config import get_settings


class TextToSpeechService(ABC):
    """Abstract interface for speech synthesis."""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        output_path: Optional[Union[Path, str]] = None,
        instructions: Optional[str] = None,
    ) -> bytes:
        """Synthesize text to audio bytes (MP3), optionally saving to disk."""
        ...

    @abstractmethod
    def synthesize_mulaw(
        self,
        text: str,
        instructions: Optional[str] = None,
    ) -> bytes:
        """Synthesize text directly to 8kHz 8-bit G.711 mu-law bytes for telephony."""
        ...


class OpenAITTSService(TextToSpeechService):
    """OpenAI TTS implementation supporting gpt-4o-mini-tts and tts-1."""

    DEFAULT_PERSONA = (
        "Speak like a helpful, warm, and professional Australian customer service specialist. "
        "Clear and friendly pacing with natural pauses."
    )

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        voice: Optional[str] = None,
    ):
        settings = get_settings()
        self._api_key = api_key or settings.openai_api_key
        self._model = model or settings.openai_tts_model or "gpt-4o-mini-tts"
        self._voice = voice or settings.openai_tts_voice or "sage"
        self._client: Optional[OpenAI] = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def synthesize(
        self,
        text: str,
        output_path: Optional[Union[Path, str]] = None,
        instructions: Optional[str] = None,
    ) -> bytes:
        client = self._get_client()
        persona_instructions = instructions or self.DEFAULT_PERSONA

        kwargs = {
            "model": self._model,
            "voice": self._voice,
            "input": text,
        }

        # Some models support prompt/persona instructions
        if "mini" in self._model.lower():
            kwargs["instructions"] = persona_instructions

        try:
            with client.audio.speech.with_streaming_response.create(**kwargs) as response:
                audio_bytes = response.read()
        except TypeError:
            # Fallback if instructions is not supported by installed SDK version/model
            kwargs.pop("instructions", None)
            with client.audio.speech.with_streaming_response.create(**kwargs) as response:
                audio_bytes = response.read()

        if output_path:
            out_p = Path(output_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            with open(out_p, "wb") as f:
                f.write(audio_bytes)

        return audio_bytes

    def synthesize_mulaw(
        self,
        text: str,
        instructions: Optional[str] = None,
    ) -> bytes:
        """Synthesize text directly to 8kHz 8-bit G.711 mu-law bytes for telephony."""
        from app.services.audio_codec import pcm16_to_mulaw, resample_pcm16

        client = self._get_client()
        persona_instructions = instructions or self.DEFAULT_PERSONA

        kwargs = {
            "model": self._model,
            "voice": self._voice,
            "input": text,
            "response_format": "pcm",  # Returns 24kHz 16-bit mono PCM
        }

        if "mini" in self._model.lower():
            kwargs["instructions"] = persona_instructions

        try:
            with client.audio.speech.with_streaming_response.create(**kwargs) as response:
                pcm24k_bytes = response.read()
        except (TypeError, Exception):
            kwargs.pop("instructions", None)
            with client.audio.speech.with_streaming_response.create(**kwargs) as response:
                pcm24k_bytes = response.read()

        # Resample 24kHz -> 8kHz, then encode to mu-law
        pcm8k = resample_pcm16(pcm24k_bytes, in_rate=24000, out_rate=8000)
        return pcm16_to_mulaw(pcm8k)


class MockTTSService(TextToSpeechService):
    """Mock TTS service that returns a tiny valid MP3 byte sequence for fast tests."""

    # Minimal silent MP3 frame bytes
    SILENT_MP3_FRAME = b"\xff\xfb\x90d\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"

    def synthesize(
        self,
        text: str,
        output_path: Optional[Union[Path, str]] = None,
        instructions: Optional[str] = None,
    ) -> bytes:
        audio_data = self.SILENT_MP3_FRAME * 10
        if output_path:
            out_p = Path(output_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            with open(out_p, "wb") as f:
                f.write(audio_data)
        return audio_data

    def synthesize_mulaw(
        self,
        text: str,
        instructions: Optional[str] = None,
    ) -> bytes:
        # Returns 0.4 seconds of 8kHz silence (G.711 mu-law 0xFF is silent)
        return b"\xff" * 3200
