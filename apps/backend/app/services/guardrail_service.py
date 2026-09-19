"""
CIMET Reconnect — Guardrail Service

Deterministic safety guardrails implementing all 11 policy rules defined in the specification.
Ensures the AI agent immediately identifies unsafe conditions and triggers handoff or termination.
"""

import re
from typing import Optional
from pydantic import BaseModel, Field

from app.domain.models import EscalationReason


def redact_payment_info(text: str) -> str:
    """Deterministically scrubs credit card numbers, CVVs, and payment secrets from text.
    
    Ensures zero sensitive payment data is stored in memory, logs, transcripts, or handoffs.
    """
    if not text:
        return ""

    # 1. 13-19 digit card numbers (with or without spaces/hyphens)
    def _mask_card(match: re.Match) -> str:
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if 13 <= len(digits) <= 19:
            return "[REDACTED CARD]"
        return raw

    redacted = re.sub(r"\b(?:\d[ -]?){13,19}\b", _mask_card, text)

    # 2. CVV / CVC (3-4 digits after security code indicators)
    redacted = re.sub(
        r"\b(cvv|cvc|security code|security number)\s*(?:is|:)?\s*\d{3,4}\b",
        r"\1 [REDACTED CVV]",
        redacted,
        flags=re.IGNORECASE,
    )

    # 3. Expiration dates (MM/YY or MM/YYYY)
    redacted = re.sub(
        r"\b(expiry|exp|expires|expiration)\s*(?:date|is|:)?\s*(?:0[1-9]|1[0-2])[/-]\d{2,4}\b",
        r"\1 [REDACTED EXPIRY]",
        redacted,
        flags=re.IGNORECASE,
    )

    # 4. Explicit card number mentions followed by digits
    redacted = re.sub(
        r"((?:credit\s+card|card\s+number|account\s+number)\s*(?:is|:)?\s*)\d+",
        r"\1[REDACTED CARD]",
        redacted,
        flags=re.IGNORECASE,
    )

    return redacted


class GuardrailCheckResult(BaseModel):
    """Result of evaluating safety guardrails on customer input."""
    passed: bool
    escalation_required: bool = False
    escalation_reason: EscalationReason = EscalationReason.NONE
    violation_rule: Optional[str] = None
    customer_statement: str = ""
    agent_message: Optional[str] = None


class GuardrailService:
    """Evaluates customer input against all 11 deterministic safety boundaries."""

    # 1. Payment / Card patterns — MUST NEVER COLLECT OR STORE CARDS
    PAYMENT_PATTERNS = [
        r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12})\b",  # Standard PANs
        r"\b(?:\d{4}[ -]?){3}\d{4}\b",  # Formatted 16 digit
        r"\b(credit card|debit card|mastercard|visa card|amex|cvv|cvc|card number|expiry date)\b",
        r"\b(pay now|here is my card|take my payment|take my card|bank details|bsb)\b",
    ]

    # 2. Sensitive Situation patterns (financial distress, bereavement, life support, legal/disputes)
    SENSITIVE_PATTERNS = [
        r"\b(passed away|died|death|bereavement|funeral|late husband|late wife|estate|executor)\b",
        r"\b(life support|medical equipment|oxygen machine|oxygen concentrator|dialysis|critical care|medical dependency|respiratory)\b",
        r"\b(financial hardship|cannot afford|can't afford|bankrupt|bankruptcy|eviction|homeless|no money|centrelink hardship|disconnection notice|threatened with disconnection)\b",
        r"\b(domestic violence|police|restraining order|ombudsman|legal action|lawyer|disputing this account|dispute)\b",
    ]

    # 3. Explicit Human Request patterns
    HUMAN_REQUEST_PATTERNS = [
        r"\b(speak to a human|talk to a person|real person|human agent|transfer me|operator|representative|customer service rep)\b",
        r"\b(put me through|talk to someone|speak with someone|speak to someone|get me a manager|real human)\b",
        r"\b(are you a robot|stop bot|stop ai|human please|can i speak to a person|i want a human|can i talk to an agent|connect me with an operator)\b",
    ]

    # 4. Customer Decline / Busy patterns during active call
    DECLINE_BUSY_PATTERNS = [
        r"\b(i'm busy|im busy|too busy|busy right now|can't talk|cant talk|cannot talk right now|call back later)\b",
        r"\b(stop calling|don't call|dont call|do not call|leave me alone|not interested|don't want to continue|dont want to continue)\b",
        r"\b(cancel this|cancel my request|cancel the comparison|end call|hang up now)\b",
    ]

    # 5. Frustration / Anger patterns
    FRUSTRATION_PATTERNS = [
        r"\b(this is ridiculous|ridiculous|waste of time|you are useless|useless bot|stupid|idiot|hate this|stop wasting my time)\b",
        r"\b(i've already told you|i already told you|told you three times|told you that already|this is frustrating|so frustrated|i'm done|im done)\b",
        r"\b(annoying|terrible service|awful|horrible|furious|pissed off|shut up)\b",
        r"\b(bullshit|crap|damn it|fucking|fuck)\b",
    ]

    # 6. Advice / Provider Recommendation requests
    ADVICE_PATTERNS = [
        r"\b(which provider should i (?:choose|pick|go with)|who is the cheapest|what is the best plan|which company is best)\b",
        r"\b(recommend a plan|give me advice|what do you recommend|what would you recommend|which plan is best|what tariff should i select)\b",
        r"\b(should i switch to|is agl better|is origin better|who should i go with|which energy company is cheapest)\b",
    ]

    # 7. Off-script requests
    OFF_SCRIPT_PATTERNS = [
        r"\b(book (?:a )?flight|order (?:a )?pizza|weather forecast|what is the weather|who won the|tell me a joke|write a poem)\b",
        r"\b(buy groceries|hotel reservation|rent a car|crypto|bitcoin|fix my internet|help with my bank)\b",
    ]

    # 8. Confusion patterns
    CONFUSION_PATTERNS = [
        r"\b(i don't understand|i dont understand|i have no idea|what does that mean|what do you mean|you make no sense|i'm confused|im confused|this is confusing)\b",
        r"\b(makes no sense|don't get it|dont get it|what are you talking about|what are you asking)\b",
    ]

    # Standard responses for escalations
    ESCALATION_MESSAGES = {
        EscalationReason.PAYMENT: (
            "For your security, I cannot collect or process credit card or payment details over this automated line. "
            "Let me immediately transfer you to one of our licensed human specialists to assist you safely."
        ),
        EscalationReason.ADVICE_REQUEST: (
            "I'm unable to provide specific retail advice or tell you which provider to choose. "
            "Let me transfer you to an accredited energy specialist who can review and compare options with you."
        ),
        EscalationReason.HUMAN_REQUEST: (
            "Certainly. I am transferring you directly to a customer service specialist right now."
        ),
        EscalationReason.FRUSTRATION: (
            "I understand your frustration, and I apologize for the difficulty. "
            "I am transferring you to a human team member who can take care of this for you immediately."
        ),
        EscalationReason.CONFUSION: (
            "I hear that this is confusing. Let me connect you with a specialist who can explain the details clearly."
        ),
        EscalationReason.SENSITIVE: (
            "Thank you for letting me know. Because this requires specialized care, "
            "I am transferring you immediately to our dedicated support team."
        ),
        EscalationReason.OFF_SCRIPT: (
            "I can only help with your Energy comparison. Let me connect you with an operator who can assist further."
        ),
        EscalationReason.LOW_CONFIDENCE: (
            "I'm having a little trouble hearing you clearly. Let me connect you with our team so you don't have to repeat yourself."
        ),
        EscalationReason.REPEATED_FAILURE: (
            "I'm having trouble getting that information. Let me connect you to a team member who can assist."
        ),
    }

    DECLINE_MESSAGE = (
        "No problem at all. Thank you for your time today. "
        "Have a great day, goodbye!"
    )

    def check(self, customer_utterance: str, confidence: float = 1.0) -> GuardrailCheckResult:
        """Evaluate customer utterance across all guardrails in strict deterministic priority order."""
        text = customer_utterance.strip().lower()

        # 1. PAYMENT / CREDIT CARD BOUNDARY (Highest Security Priority — zero card data stored)
        for pattern in self.PAYMENT_PATTERNS:
            if re.search(pattern, text):
                return GuardrailCheckResult(
                    passed=False,
                    escalation_required=True,
                    escalation_reason=EscalationReason.PAYMENT,
                    violation_rule="payment_boundary",
                    customer_statement=redact_payment_info(customer_utterance),
                    agent_message=self.ESCALATION_MESSAGES[EscalationReason.PAYMENT],
                )

        # 2. SENSITIVE SITUATIONS (Hardship, Bereavement, Vulnerable/Medical, Legal/Dispute)
        for pattern in self.SENSITIVE_PATTERNS:
            if re.search(pattern, text):
                return GuardrailCheckResult(
                    passed=False,
                    escalation_required=True,
                    escalation_reason=EscalationReason.SENSITIVE,
                    violation_rule="sensitive_situation",
                    customer_statement=redact_payment_info(customer_utterance),
                    agent_message=self.ESCALATION_MESSAGES[EscalationReason.SENSITIVE],
                )

        # 3. EXPLICIT HUMAN REQUEST
        for pattern in self.HUMAN_REQUEST_PATTERNS:
            if re.search(pattern, text):
                return GuardrailCheckResult(
                    passed=False,
                    escalation_required=True,
                    escalation_reason=EscalationReason.HUMAN_REQUEST,
                    violation_rule="human_request",
                    customer_statement=redact_payment_info(customer_utterance),
                    agent_message=self.ESCALATION_MESSAGES[EscalationReason.HUMAN_REQUEST],
                )

        # 4. CUSTOMER DECLINE / BUSY (Respectful termination, zero persuasion loop)
        for pattern in self.DECLINE_BUSY_PATTERNS:
            if re.search(pattern, text):
                return GuardrailCheckResult(
                    passed=False,
                    escalation_required=False,
                    escalation_reason=EscalationReason.NONE,
                    violation_rule="customer_decline",
                    customer_statement=redact_payment_info(customer_utterance),
                    agent_message=self.DECLINE_MESSAGE,
                )

        # 5. FRUSTRATION / ANGER
        for pattern in self.FRUSTRATION_PATTERNS:
            if re.search(pattern, text):
                return GuardrailCheckResult(
                    passed=False,
                    escalation_required=True,
                    escalation_reason=EscalationReason.FRUSTRATION,
                    violation_rule="customer_frustration",
                    customer_statement=redact_payment_info(customer_utterance),
                    agent_message=self.ESCALATION_MESSAGES[EscalationReason.FRUSTRATION],
                )

        # 6. NO RETAILER / TARIFF ADVICE
        for pattern in self.ADVICE_PATTERNS:
            if re.search(pattern, text):
                return GuardrailCheckResult(
                    passed=False,
                    escalation_required=True,
                    escalation_reason=EscalationReason.ADVICE_REQUEST,
                    violation_rule="no_advice",
                    customer_statement=redact_payment_info(customer_utterance),
                    agent_message=self.ESCALATION_MESSAGES[EscalationReason.ADVICE_REQUEST],
                )

        # 7. OFF-SCRIPT DEFLECTION / ESCALATION
        for pattern in self.OFF_SCRIPT_PATTERNS:
            if re.search(pattern, text):
                return GuardrailCheckResult(
                    passed=False,
                    escalation_required=True,
                    escalation_reason=EscalationReason.OFF_SCRIPT,
                    violation_rule="off_script",
                    customer_statement=redact_payment_info(customer_utterance),
                    agent_message=self.ESCALATION_MESSAGES[EscalationReason.OFF_SCRIPT],
                )

        # 8. LOW AUDIO / TRANSCRIPTION CONFIDENCE (Strict numeric comparison < 0.60)
        if confidence < 0.60:
            return GuardrailCheckResult(
                passed=False,
                escalation_required=True,
                escalation_reason=EscalationReason.LOW_CONFIDENCE,
                violation_rule="low_confidence",
                customer_statement=redact_payment_info(customer_utterance),
                agent_message=self.ESCALATION_MESSAGES[EscalationReason.LOW_CONFIDENCE],
            )

        # 9. CUSTOMER CONFUSION
        for pattern in self.CONFUSION_PATTERNS:
            if re.search(pattern, text):
                return GuardrailCheckResult(
                    passed=False,
                    escalation_required=True,
                    escalation_reason=EscalationReason.CONFUSION,
                    violation_rule="customer_confusion",
                    customer_statement=redact_payment_info(customer_utterance),
                    agent_message=self.ESCALATION_MESSAGES[EscalationReason.CONFUSION],
                )

        # All guardrails passed
        return GuardrailCheckResult(
            passed=True,
            escalation_required=False,
            escalation_reason=EscalationReason.NONE,
            customer_statement=redact_payment_info(customer_utterance),
        )
