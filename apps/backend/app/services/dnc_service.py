"""
CIMET Reconnect — Do-Not-Call (DNC) Service

Verifies whether a phone number is registered on the Do-Not-Call register
prior to initiating any outbound voice interaction.
"""

from abc import ABC, abstractmethod
from typing import Optional, Set
from pydantic import BaseModel, Field


class DNCResult(BaseModel):
    """Result of a Do-Not-Call verification check."""
    phone_number: str
    allowed: bool
    reason: Optional[str] = None
    provider: str = "mock"


class DNCService(ABC):
    """Abstract interface for Do-Not-Call verification."""

    @abstractmethod
    def check(self, phone_number: str) -> DNCResult:
        """Check if a phone number is permitted to be contacted."""
        ...


class MockDNCService(DNCService):
    """Development/testing implementation with configurable blocked numbers.
    
    By default, numbers explicitly added to the blocklist are rejected.
    Special test cases can be triggered by specific numbers or suffixes.
    """

    DEFAULT_BLOCKED_NUMBERS: Set[str] = {
        "+61400000999",
        "+61400000666",
        "+61000000000",
        "DNC-BLOCKED",
    }

    def __init__(self, blocked_numbers: Optional[Set[str]] = None):
        self._blocked = set(blocked_numbers) if blocked_numbers is not None else set(self.DEFAULT_BLOCKED_NUMBERS)

    def block_number(self, phone_number: str) -> None:
        """Add a number to the blocklist."""
        self._blocked.add(phone_number.strip())

    def unblock_number(self, phone_number: str) -> None:
        """Remove a number from the blocklist."""
        self._blocked.discard(phone_number.strip())

    def check(self, phone_number: str) -> DNCResult:
        """Check if phone number is blocked."""
        clean_num = phone_number.strip()
        
        # Check explicit blocklist or known test suffix
        if clean_num in self._blocked or clean_num.endswith("999"):
            return DNCResult(
                phone_number=clean_num,
                allowed=False,
                reason="Phone number is registered on Do-Not-Call register",
                provider="mock",
            )
        
        return DNCResult(
            phone_number=clean_num,
            allowed=True,
            reason="Clear to call",
            provider="mock",
        )
