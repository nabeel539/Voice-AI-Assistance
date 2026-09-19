"""
CIMET Reconnect — Consent Service

Handles mandatory recording and participation consent before any customer
information is collected. Strictly enforces call termination on decline.
"""

import re
from typing import Tuple, Optional
from pydantic import BaseModel
from app.domain.call_state import ConsentStatus


class ConsentEvaluation(BaseModel):
    """Result of evaluating a customer's response to the consent question."""
    status: ConsentStatus
    confidence: float
    detected_intent: str
    response_script: str


class ConsentService:
    """Evaluates customer consent responses deterministically with regex and fallback."""

    CONSENT_PROMPT = (
        "Hey there, Emma here from CIMET! You recently started an energy comparison with us, "
        "so I'm calling to help you pick up where you left off. Before we continue, I just need to "
        "let you know this call is recorded for quality and training purposes. Are you happy to go ahead?"
    )

    DECLINE_RESPONSE = (
        "No problem at all. Thank you for your time today. "
        "Have a great day, goodbye!"
    )

    AFFIRMATIVE_RESPONSE = (
        "Awesome, thank you! Let's pick up right where you left off."
    )

    CLARIFY_RESPONSE = (
        "Just to confirm, we record our calls for training and quality assurance. "
        "Are you happy for us to proceed with your energy comparison?"
    )

    # Affirmative patterns
    AFFIRMATIVE_PATTERNS = [
        r"\b(yes|yeah|yep|sure|ok|okay|fine|go ahead|proceed|no problem|sounds good|alright|that's fine|correct|yup)\b",
        r"\b(i agree|i consent|continue|please do|that's okay|all good|speaking)\b",
    ]

    # Negative / Decline patterns
    DECLINE_PATTERNS = [
        r"\b(no|nope|not interested|stop|don't call|do not call|don't want|hang up|cancel|leave me alone)\b",
        r"\b(not now|don't record|no recording|do not record|i decline|i do not consent|i don't consent)\b",
        r"\b(remove me|take me off|busy right now|never call)\b",
    ]

    def get_consent_prompt(self, customer_name: str = "") -> str:
        """Get the initial consent question text using warm conversational Emma persona."""
        cleaned_name = customer_name.strip()
        if cleaned_name:
            return (
                f"Hey {cleaned_name}, Emma here from CIMET! You recently started an energy comparison with us, "
                "so I'm calling to help you pick up where you left off. Before we continue, I just need to "
                "let you know this call is recorded for quality and training purposes. Are you happy to go ahead?"
            )
        return self.CONSENT_PROMPT

    @staticmethod
    def detect_name_correction(text: str) -> Tuple[bool, Optional[str]]:
        """Detect if customer corrects their name in their response (e.g. 'No my name is Sarah', 'This is John')."""
        clean_text = text.strip()
        patterns = [
            r"(?:my name(?:'s| is)|i am|i'm|this is|actually it's|call me)\s+([A-Z][a-z]+|[a-z]+)",
            r"(?:not\s+[A-Z]?[a-z]+[,\s]+(?:it's|i'm|i am|this is)\s+)([A-Z][a-z]+|[a-z]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip().capitalize()
                # Exclude common non-name words
                if candidate.lower() not in ("yes", "no", "sure", "fine", "okay", "good", "happy", "interested", "not", "ready"):
                    return True, candidate
        return False, None

    def evaluate(self, customer_utterance: str) -> ConsentEvaluation:
        """Evaluate customer utterance for recording and continuation consent."""
        text = customer_utterance.strip().lower()

        # Check affirmative idioms containing 'no' (e.g. "no problem", "no worries")
        if re.search(r"\b(no problem|no worries|no issue|not a problem)\b", text):
            return ConsentEvaluation(
                status=ConsentStatus.CONSENTED,
                confidence=0.95,
                detected_intent="affirmative",
                response_script=self.AFFIRMATIVE_RESPONSE,
            )

        # If 'no' is part of a name correction (e.g. "No, my name is Sarah, but yes..."),
        # strip that clause so the actual consent intent is evaluated accurately
        eval_text = re.sub(r"\bno\b[,\s]+(?:my\s+name\s+is|my\s+name's|i'm|i\s+am|this\s+is|it's)\b[^,;]+(?:[,\s]*(?:but|and))?", " ", text).strip()
        if not eval_text:
            eval_text = text

        # Check declines (safety priority)
        for pattern in self.DECLINE_PATTERNS:
            if re.search(pattern, eval_text):
                return ConsentEvaluation(
                    status=ConsentStatus.DECLINED,
                    confidence=0.95,
                    detected_intent="decline",
                    response_script=self.DECLINE_RESPONSE,
                )

        # Check affirmative
        for pattern in self.AFFIRMATIVE_PATTERNS:
            if re.search(pattern, eval_text):
                return ConsentEvaluation(
                    status=ConsentStatus.CONSENTED,
                    confidence=0.95,
                    detected_intent="affirmative",
                    response_script=self.AFFIRMATIVE_RESPONSE,
                )

        # Ambiguous / Unclear -> Pending
        return ConsentEvaluation(
            status=ConsentStatus.PENDING,
            confidence=0.50,
            detected_intent="unclear",
            response_script=self.CLARIFY_RESPONSE,
        )
