"""
CIMET Reconnect — Comprehensive Deterministic Safety Guardrails Test Matrix

Verifies all 11 required deterministic safety rules across 20 distinct evaluation scenarios:
1. Happy path (full end-to-end recovery + submission)
2. Misheard answer (clarify & resume)
3. Invalid answer (validation & retry)
4. Customer busy (respectful decline during active call)
5. Not interested / decline (respectful decline during consent)
6. Customer frustration (immediate handoff with context)
7. Explicit human request (immediate handoff)
8. Payment / card boundary (zero card data stored anywhere)
9. Off-script deflection / escalation (unsupported topics)
10. Advice request (no retailer/tariff recommendation)
11. Low audio confidence (strict numeric boundary tests: 0.59, 0.60, 0.61)
12. Confusion & retries (first confusion clarifies, repeated confusion escalates)
13. Financial hardship (sensitive situation escalation)
14. Bereavement (sensitive situation escalation)
15. Medical equipment / life support (sensitive situation escalation)
16. Legal / ombudsman dispute (sensitive situation escalation)
17. Consent explicitly declined (clean termination)
18. Field processing attempted before consent (mandatory gate blocked)
19. DNC blocked (verification fails before call initiation)
20. DNC allowed (verification passes, call begins)
"""

import pytest
from app.agent.graph import EnergyRecoveryAgent
from app.domain.call_state import CallState
from app.domain.models import CallStatus, ConsentStatus, EscalationReason, JourneyStep
from app.services.dataset_adapter import MockDatasetAdapter
from app.services.dnc_service import MockDNCService
from app.services.guardrail_service import redact_payment_info


@pytest.fixture
def agent():
    return EnergyRecoveryAgent()


@pytest.fixture
def adapter():
    return MockDatasetAdapter()


# ─── 1. Happy Path ─────────────────────────────────────────────────────────────
def test_scenario_01_happy_path(agent, adapter):
    """Full cooperant customer journey completing all fields and sandbox submission."""
    lead = adapter.get_lead("ENG-DEMO-003")
    state = CallState.from_lead(lead)
    state.collected_fields = {
        "address": "42 Market Street", "suburb": "Melbourne", "postcode": "3000",
        "energy_type": "electricity", "electricity_meter_type": "smart", "has_solar": False,
        "electricity_usage": 950, "usage_period": "quarterly",
    }
    
    # 1. Start Call & DNC
    t0 = agent.start_call(state)
    assert t0["status"] == "active"
    assert state.dnc_allowed is True
    
    # 2. Consent
    t1 = agent.process_turn(state, "Yes, absolutely, I agree")
    assert state.consent_status == ConsentStatus.CONSENTED
    assert state.current_field == "first_name"
    
    # 3. Collect Customer Details
    agent.process_turn(state, "My first name is Sarah")
    assert state.collected_fields["first_name"] == "Sarah"
    agent.process_turn(state, "Jenkins")
    assert state.collected_fields["last_name"] == "Jenkins"
    t4 = agent.process_turn(state, "sarah.j@example.com")
    
    # 4. Final Submission
    assert t4["status"] == "completed"
    assert state.call_status == CallStatus.COMPLETED
    assert t4["submission_result"].status.value == "submitted"
    assert "cimet" in t4["submission_result"].reference_id.lower()


# ─── 2. Misheard Answer ────────────────────────────────────────────────────────
def test_scenario_02_misheard_answer(agent):
    """Unclear audio / mumbled speech prompts clarification and recovers on second attempt."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)
    state.current_field = "postcode"

    t1 = agent.process_turn(state, "err... mumble... not sure")
    assert t1["status"] == "active"
    assert state.retry_count == 1
    assert "postcode" not in state.collected_fields

    t2 = agent.process_turn(state, "3000")
    assert t2["status"] == "active"
    assert state.collected_fields["postcode"] == "3000"
    assert state.retry_count == 0


# ─── 3. Invalid Answer ────────────────────────────────────────────────────────
def test_scenario_03_invalid_answer(agent):
    """Invalid input format triggers corrective guidance and saves once valid."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)
    state.current_field = "email"

    t1 = agent.process_turn(state, "my email is just john at somewhere")
    assert t1["status"] == "active"
    assert "email" not in state.collected_fields

    t2 = agent.process_turn(state, "john@example.com")
    assert t2["status"] == "active"
    assert state.collected_fields["email"] == "john@example.com"


# ─── 4. Customer Busy (Active Turn) ───────────────────────────────────────────
def test_scenario_04_customer_busy(agent):
    """Customer states they are busy mid-call; call respectfully terminates with zero pressure."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)
    state.current_field = "postcode"

    t1 = agent.process_turn(state, "I'm really busy right now, can't talk")
    assert t1["status"] == "declined"
    assert state.call_status == CallStatus.DECLINED
    assert "postcode" not in state.collected_fields
    assert "goodbye" in t1["agent_message"].lower()


# ─── 5. Not Interested / Decline ──────────────────────────────────────────────
def test_scenario_05_not_interested(agent):
    """Customer states they are not interested; call terminates without persuasion loop."""
    state = CallState(lead_id="ENG-DEMO-001")
    agent.start_call(state)

    t1 = agent.process_turn(state, "I am not interested, please stop calling me")
    assert t1["status"] == "declined"
    assert state.call_status == CallStatus.DECLINED
    assert state.consent_status == ConsentStatus.DECLINED
    assert len(state.collected_fields) == 0


# ─── 6. Frustration / Anger ───────────────────────────────────────────────────
def test_scenario_06_frustration(agent):
    """Customer expresses anger/frustration; immediate warm handoff with safe context."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)
    state.current_field = "postcode"

    t1 = agent.process_turn(state, "I've already told you this three times, this bot is completely useless!")
    assert t1["status"] == "handed_off"
    assert state.call_status == CallStatus.HANDOFF
    assert t1["handoff_package"].escalation_reason == EscalationReason.FRUSTRATION
    assert "postcode" in t1["handoff_package"].missing_fields


# ─── 7. Human Request ─────────────────────────────────────────────────────────
def test_scenario_07_human_request(agent):
    """Customer asks to talk to a human operator; immediate handoff without asking another question."""
    state = CallState(lead_id="ENG-DEMO-001")
    agent.start_call(state)

    t1 = agent.process_turn(state, "Can I speak to a person please?")
    assert t1["status"] == "handed_off"
    assert state.call_status == CallStatus.HANDOFF
    assert t1["handoff_package"].escalation_reason == EscalationReason.HUMAN_REQUEST


# ─── 8. Payment / Credit Card Boundary (Zero Card Data Stored) ────────────────
def test_scenario_08_payment_boundary_zero_data_stored(agent):
    """Customer provides 16-digit card and CVV; system MUST escalate and scrub card data completely."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)
    raw_card_input = "Can I just pay with my Visa card 4532 1111 2222 3333 cvv 888?"

    t1 = agent.process_turn(state, raw_card_input)
    assert t1["status"] == "handed_off"
    assert state.call_status == CallStatus.HANDOFF
    assert t1["handoff_package"].escalation_reason == EscalationReason.PAYMENT

    # CRITICAL: Verify zero credit card numbers or CVVs appear in collected fields
    for k, v in state.collected_fields.items():
        assert "4532" not in str(v)
        assert "888" not in str(v)

    # Verify handoff customer statement is redacted
    assert "4532" not in t1["handoff_package"].customer_statement
    assert "[REDACTED" in t1["handoff_package"].customer_statement

    # Verify summary is safe
    assert "payment/card-related issue" in t1["handoff_package"].summary
    assert "4532" not in t1["handoff_package"].summary

    # Redaction utility verification
    sanitized = redact_payment_info("Here is card 5100 1234 5678 9012 with cvv 123 exp 12/28")
    assert "5100" not in sanitized
    assert "123" not in sanitized
    assert "[REDACTED CARD]" in sanitized
    assert "[REDACTED CVV]" in sanitized


# ─── 9. Off-Script Deflection / Escalation ────────────────────────────────────
def test_scenario_09_off_script(agent):
    """Customer asks unrelated off-script request; escalates to human without hallucinating."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)

    t1 = agent.process_turn(state, "What is the weather forecast for Sydney tomorrow?")
    assert t1["status"] == "handed_off"
    assert t1["handoff_package"].escalation_reason == EscalationReason.OFF_SCRIPT


# ─── 10. Advice Request (Multiple Phrasings) ──────────────────────────────────
@pytest.mark.parametrize("advice_prompt", [
    "Which provider should I choose between AGL and EnergyAustralia?",
    "What is the best plan for my household?",
    "What tariff should I select for solar?",
    "What would you recommend for me?",
    "Who is the cheapest energy company?",
])
def test_scenario_10_advice_request_phrasings(agent, advice_prompt):
    """AI refuses to provide retail comparison advice and transfers to accredited human specialist."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)

    t = agent.process_turn(state, advice_prompt)
    assert t["status"] == "handed_off"
    assert t["handoff_package"].escalation_reason == EscalationReason.ADVICE_REQUEST
    assert "advice" in t["agent_message"].lower() or "specialist" in t["agent_message"].lower()


# ─── 11. Low Audio Confidence Numeric Boundary Tests ─────────────────────────
def test_scenario_11_low_confidence_boundary(agent):
    """Strict numeric check: confidence < 0.60 triggers handoff; >= 0.60 continues."""
    # 1. 0.59 -> Below threshold -> Escalates
    state1 = CallState(lead_id="ENG-DEMO-001")
    state1.mark_consent(ConsentStatus.CONSENTED)
    t_low = agent.process_turn(state1, "3000", confidence=0.59)
    assert t_low["status"] == "handed_off"
    assert t_low["handoff_package"].escalation_reason == EscalationReason.LOW_CONFIDENCE

    # 2. 0.60 -> Exact threshold boundary -> Allowed to proceed
    state2 = CallState(lead_id="ENG-DEMO-001")
    state2.mark_consent(ConsentStatus.CONSENTED)
    state2.current_field = "postcode"
    t_boundary = agent.process_turn(state2, "3000", confidence=0.60)
    assert t_boundary["status"] == "active"
    assert state2.collected_fields.get("postcode") == "3000"

    # 3. 0.61 -> Above threshold -> Allowed to proceed
    state3 = CallState(lead_id="ENG-DEMO-001")
    state3.mark_consent(ConsentStatus.CONSENTED)
    state3.current_field = "postcode"
    t_high = agent.process_turn(state3, "3000", confidence=0.61)
    assert t_high["status"] == "active"
    assert state3.collected_fields.get("postcode") == "3000"


# ─── 12. Confusion: First Clarifies, Repeated Escalates ───────────────────────
def test_scenario_12_confusion_clarification_then_escalation(agent):
    """First confusion clarifies question; repeated confusion escalates to human."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)
    state.current_field = "postcode"

    # Turn 1: First confusion -> Clarify
    t1 = agent.process_turn(state, "I don't understand what you mean")
    assert t1["status"] == "active"
    assert state.retry_count == 1
    assert "clarify" in t1["agent_message"].lower()

    # Turn 2: Repeated confusion -> Escalates to Human Handoff
    t2 = agent.process_turn(state, "This makes no sense to me at all")
    assert t2["status"] == "handed_off"
    assert state.call_status == CallStatus.HANDOFF
    assert t2["handoff_package"].escalation_reason == EscalationReason.CONFUSION


# ─── 13. Sensitive: Financial Hardship ────────────────────────────────────────
def test_scenario_13_sensitive_hardship(agent):
    """Customer mentions inability to afford or financial hardship; immediate compassionate handoff."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)

    t = agent.process_turn(state, "I'm in financial hardship and facing an eviction notice right now")
    assert t["status"] == "handed_off"
    assert state.call_status == CallStatus.HANDOFF
    assert t["handoff_package"].escalation_reason == EscalationReason.SENSITIVE


# ─── 14. Sensitive: Bereavement ───────────────────────────────────────────────
def test_scenario_14_sensitive_bereavement(agent):
    """Customer mentions deceased spouse/bereavement; immediate transfer to dedicated care."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)

    t = agent.process_turn(state, "My late husband passed away recently and I am managing his estate")
    assert t["status"] == "handed_off"
    assert state.call_status == CallStatus.HANDOFF
    assert t["handoff_package"].escalation_reason == EscalationReason.SENSITIVE


# ─── 15. Sensitive: Medical Equipment / Life Support ──────────────────────────
def test_scenario_15_sensitive_medical_equipment(agent):
    """Customer mentions home dialysis or life support; immediate vulnerable customer escalation."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)

    t = agent.process_turn(state, "We have life support medical equipment and an oxygen machine at this address")
    assert t["status"] == "handed_off"
    assert state.call_status == CallStatus.HANDOFF
    assert t["handoff_package"].escalation_reason == EscalationReason.SENSITIVE


# ─── 16. Sensitive: Dispute / Legal Action ────────────────────────────────────
def test_scenario_16_sensitive_dispute(agent):
    """Customer mentions ombudsman or legal dispute; immediate handoff to specialist."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.mark_consent(ConsentStatus.CONSENTED)

    t = agent.process_turn(state, "I have lodged an ombudsman complaint regarding this account dispute")
    assert t["status"] == "handed_off"
    assert state.call_status == CallStatus.HANDOFF
    assert t["handoff_package"].escalation_reason == EscalationReason.SENSITIVE


# ─── 17. Consent Explicitly Declined ─────────────────────────────────────────
def test_scenario_17_consent_declined(agent):
    """Customer refuses recording consent; call terminates cleanly without data collection."""
    state = CallState(lead_id="ENG-DEMO-001")
    agent.start_call(state)

    t = agent.process_turn(state, "No, I do not consent to being recorded")
    assert t["status"] == "declined"
    assert state.consent_status == ConsentStatus.DECLINED
    assert state.call_status == CallStatus.DECLINED
    assert len(state.collected_fields) == 0


# ─── 18. Field Collection Attempted Prior to Consent ──────────────────────────
def test_scenario_18_field_attempt_before_consent_blocked(agent):
    """Direct field inputs before consent is given are NOT mapped to journey fields."""
    state = CallState(lead_id="ENG-DEMO-001")
    agent.start_call(state)
    assert state.consent_status == ConsentStatus.PENDING

    # Customer speaks something that looks like an address or email before giving consent
    t = agent.process_turn(state, "My email is john@example.com")
    assert state.consent_status != ConsentStatus.CONSENTED
    assert "email" not in state.collected_fields


# ─── 19. Do-Not-Call (DNC) Blocked ────────────────────────────────────────────
def test_scenario_19_dnc_blocked(agent):
    """DNC-blocked number prevents call initiation and active session creation."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.collected_fields["phone"] = "+61400000999"  # Registered DNC number

    t = agent.start_call(state)
    assert t["status"] == "dnc_blocked"
    assert state.dnc_allowed is False
    assert state.call_status == CallStatus.DECLINED
    assert "Do-Not-Call" in t["agent_message"]


# ─── 20. Do-Not-Call (DNC) Allowed ────────────────────────────────────────────
def test_scenario_20_dnc_allowed(agent):
    """Clear phone number passes DNC verification and initiates recording consent."""
    state = CallState(lead_id="ENG-DEMO-001")
    state.collected_fields["phone"] = "+61412345678"

    t = agent.start_call(state)
    assert t["status"] == "active"
    assert state.dnc_allowed is True
    assert "recorded" in t["agent_message"].lower()
