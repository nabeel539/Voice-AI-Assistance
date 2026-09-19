"""
CIMET Reconnect — Real-Time Telemetry & Testing Logger

Maintains an in-memory ring buffer of structured diagnostic events for phone,
voice stream, STT, agent, guardrails, and TTS testing.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TelemetryEvent(BaseModel):
    """Structured telemetry event for live testing observation."""
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    level: str = "INFO"  # "INFO" | "SUCCESS" | "WARNING" | "ERROR" | "SPEECH" | "AGENT"
    category: str = "telephony"  # "telephony" | "stt" | "agent" | "tts" | "guardrails" | "dnc" | "state"
    call_id: Optional[str] = None
    event: str
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TelemetryLogger:
    """In-memory ring buffer capturing real-time test events."""

    def __init__(self, max_events: int = 500):
        self._events: List[TelemetryEvent] = []
        self._max_events = max_events

    def log(
        self,
        event: str,
        message: str,
        level: str = "INFO",
        category: str = "telephony",
        call_id: Optional[str] = None,
        **metadata,
    ) -> TelemetryEvent:
        """Record a structured event and echo to standard logger."""
        entry = TelemetryEvent(
            timestamp=datetime.utcnow().strftime("%H:%M:%S.%f")[:-3],
            level=level,
            category=category,
            call_id=call_id,
            event=event,
            message=message,
            metadata=metadata,
        )
        self._events.append(entry)
        if len(self._events) > self._max_events:
            self._events.pop(0)

        # Colorful terminal format for live developer visibility
        prefix = f"[{entry.timestamp}] [{entry.category.upper()}] [{entry.level}]"
        print(f"{prefix} {event}: {message} {metadata if metadata else ''}")
        return entry

    def get_events(self, call_id: Optional[str] = None, limit: int = 100) -> List[TelemetryEvent]:
        """Retrieve recent events, optionally filtered by call ID."""
        if call_id:
            filtered = [e for e in self._events if e.call_id == call_id or not e.call_id]
            return filtered[-limit:]
        return self._events[-limit:]

    def clear(self):
        """Clear recorded events."""
        self._events.clear()


# Global singleton instance
telemetry_logger = TelemetryLogger()
