"""
CIMET Reconnect — Structured Extraction Service

Extracts typed field values from customer utterances with confidence scoring.
Combines deterministic regex extraction with LLM-based structured parsing fallback,
followed by mandatory validation before saving to Journey state.
"""

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.domain.models import FieldDefinition
from app.services.llm_service import LLMService
from app.services.script_engine import ScriptEngine


class ExtractedField(BaseModel):
    """Result of attempting to extract a field from customer speech."""
    field_name: str
    raw_value: Any
    confidence: float
    is_valid: bool = False
    validation_error: Optional[str] = None
    extraction_method: str = "rule"  # "rule" or "llm"
    display_value: Optional[str] = None
    unit: Optional[str] = None


class ExtractionService:
    """Service to parse and extract energy journey fields from customer responses."""

    def __init__(self, script_engine: ScriptEngine, llm_service: Optional[LLMService] = None):
        self.script_engine = script_engine
        self.llm_service = llm_service

    def extract_field(
        self,
        field_name: str,
        customer_utterance: str,
        reference_value: Optional[Any] = None,
    ) -> ExtractedField:
        """Extract a single target field from customer speech and validate it."""
        field_def = self.script_engine.get_field(field_name)
        if not field_def:
            return ExtractedField(
                field_name=field_name,
                raw_value=None,
                confidence=0.0,
                is_valid=False,
                validation_error=f"Unknown field: {field_name}",
            )

        # 0. Check reference data confirmation
        if reference_value is not None and str(reference_value).strip() != "":
            clean_text = customer_utterance.strip().lower()
            affirmation_match = bool(re.search(
                r"\b(yes|yeah|yep|yup|correct|right|that's right|thats right|sure|it is|yes it is|that's correct|thats correct|confirmed|exactly|affirmative|yes please|sounds good|all good|fine)\b",
                clean_text,
            ))
            # If user affirmed and didn't clearly provide an explicit new value, use the reference value
            has_explicit_override = False
            if field_name == "email" and ("@" in clean_text or " at " in clean_text):
                has_explicit_override = True
            elif field_name in ("first_name", "last_name") and any(clean_text.startswith(p) for p in ["no, it's", "no my", "it's actually"]):
                has_explicit_override = True

            if affirmation_match and not has_explicit_override:
                is_valid, err = self.script_engine.validate_field(field_name, reference_value)
                return ExtractedField(
                    field_name=field_name,
                    raw_value=reference_value,
                    confidence=0.99,
                    is_valid=is_valid,
                    validation_error=err,
                    extraction_method="reference_confirmation",
                    display_value=str(reference_value),
                )

        # 1. Attempt deterministic rule-based extraction
        extracted = self._rule_based_extract(field_def, customer_utterance)

        # 2. If rule-based didn't extract with high confidence and LLM is available, try LLM
        if (not extracted or extracted.raw_value is None) and self.llm_service:
            extracted = self._llm_extract(field_def, customer_utterance)

        if not extracted or extracted.raw_value is None:
            return ExtractedField(
                field_name=field_name,
                raw_value=None,
                confidence=0.0,
                is_valid=False,
                validation_error="Could not extract required information from utterance",
            )

        # 3. Deterministic Validation
        is_valid, err = self.script_engine.validate_field(field_name, extracted.raw_value)
        extracted.is_valid = is_valid
        extracted.validation_error = err

        return extracted

    def _rule_based_extract(self, field: FieldDefinition, text: str) -> Optional[ExtractedField]:
        """High-precision deterministic extraction for common patterns."""
        t = text.strip()
        name = field.name

        # Postcode: 4 digits
        if name == "postcode":
            match = re.search(r"\b(\d{4})\b", t)
            if match:
                return ExtractedField(
                    field_name=name,
                    raw_value=match.group(1),
                    confidence=0.99,
                    extraction_method="rule",
                )

        # Email
        elif name == "email":
            # Match standard email or "name at domain dot com"
            email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", t)
            if email_match:
                return ExtractedField(
                    field_name=name,
                    raw_value=email_match.group(0).lower(),
                    confidence=0.98,
                    extraction_method="rule",
                )
            spoken = re.search(r"(\w+)\s+(?:at|@)\s+(\w+)\s+(?:dot|\.)\s+(\w+)", t, re.IGNORECASE)
            if spoken:
                clean_email = f"{spoken.group(1)}@{spoken.group(2)}.{spoken.group(3)}".lower()
                return ExtractedField(
                    field_name=name,
                    raw_value=clean_email,
                    confidence=0.90,
                    extraction_method="rule",
                )

        # Solar: Boolean
        elif name == "has_solar":
            lower = t.lower()
            if re.search(r"\b(no|nope|don't|dont|do not|no solar|haven't|haven't got|none|not yet)\b", lower):
                return ExtractedField(field_name=name, raw_value=False, confidence=0.95, extraction_method="rule")
            elif re.search(r"\b(yes|yeah|yep|we do|i do|have solar|got solar|installed|we have)\b", lower):
                return ExtractedField(field_name=name, raw_value=True, confidence=0.95, extraction_method="rule")

        # Energy Type: electricity / gas / both
        elif name == "energy_type":
            lower = t.lower()
            if "both" in lower or ("electricity" in lower and "gas" in lower):
                return ExtractedField(field_name=name, raw_value="both", confidence=0.95, extraction_method="rule")
            elif "gas" in lower and "electricity" not in lower:
                return ExtractedField(field_name=name, raw_value="gas", confidence=0.95, extraction_method="rule")
            elif "electricity" in lower or "power" in lower:
                return ExtractedField(field_name=name, raw_value="electricity", confidence=0.95, extraction_method="rule")

        # Electricity Usage Period: quarterly / monthly / annual
        elif name == "usage_period":
            lower = t.lower()
            if any(w in lower for w in ["quarter", "quarterly", "3 month", "three month", "every 3", "per quarter", "each quarter", "tri-monthly"]):
                return ExtractedField(field_name=name, raw_value="quarterly", confidence=0.95, extraction_method="rule")
            elif any(w in lower for w in ["month", "monthly", "per month", "every month", "each month", "1 month", "one month"]):
                return ExtractedField(field_name=name, raw_value="monthly", confidence=0.95, extraction_method="rule")
            elif any(w in lower for w in ["year", "annual", "yearly", "per year", "every year", "12 month"]):
                return ExtractedField(field_name=name, raw_value="annual", confidence=0.95, extraction_method="rule")

        # Electricity Usage: Number (kWh or $)
        elif name == "electricity_usage":
            # Extract number (supports commas e.g. 1,200)
            match = re.search(r"(?:about|around|\$)?\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:kwh|kilowatt(?:\s+hours?)?|dollars?)?", t, re.IGNORECASE)
            if match:
                try:
                    num_str = match.group(1).replace(",", "")
                    val = float(num_str)
                    raw_val = int(val) if val.is_integer() else val

                    lower = t.lower()
                    unit = None
                    prefix = "about " if ("about" in lower or "around" in lower) else ""
                    formatted_num = f"{raw_val:,}" if isinstance(raw_val, int) else f"{raw_val}"

                    if any(u in lower for u in ["kwh", "kilowatt", "kilowatt hours", "kilowatt-hour", "kilowatt hour"]):
                        unit = "kWh"
                        display_val = f"{prefix}{formatted_num} kilowatt hours"
                    elif any(u in lower for u in ["dollar", "dollars", "$"]):
                        unit = "dollars"
                        display_val = f"{prefix}${formatted_num}"
                    else:
                        unit = None
                        display_val = f"{prefix}{formatted_num}"

                    return ExtractedField(
                        field_name=name,
                        raw_value=raw_val,
                        confidence=0.95,
                        extraction_method="rule",
                        display_value=display_val,
                        unit=unit,
                    )
                except ValueError:
                    pass

        # Meter Type: single_rate / time_of_use / unknown / smart / basic
        elif name == "electricity_meter_type":
            lower = t.lower()
            if any(w in lower for w in ["single rate", "single_rate", "single", "flat", "basic", "standard", "analog"]):
                return ExtractedField(field_name=name, raw_value="single_rate", confidence=0.95, extraction_method="rule")
            elif any(w in lower for w in ["time of use", "time_of_use", "tou", "peak", "off peak", "interval"]):
                return ExtractedField(field_name=name, raw_value="time_of_use", confidence=0.95, extraction_method="rule")
            elif any(w in lower for w in ["not sure", "don't know", "dont know", "no idea", "unknown"]):
                return ExtractedField(field_name=name, raw_value="unknown", confidence=0.95, extraction_method="rule")
            elif "smart" in lower:
                return ExtractedField(field_name=name, raw_value="single_rate", confidence=0.90, extraction_method="rule")

        # Direct text for names, address, suburb
        elif name in ["first_name", "last_name", "suburb", "address"]:
            clean = t.strip().strip(".!?,")
            # Filter common conversational prefixes
            clean = re.sub(
                r"^(?:my\s+(?:first\s+name|last\s+name|full\s+name|name|suburb|address)\s+is|it(?:'s|\s+is))\s+",
                "",
                clean,
                flags=re.IGNORECASE,
            )
            clean = re.sub(r"^(?:i'm|i\s+am)\s+", "", clean, flags=re.IGNORECASE)
            clean = clean.strip()
            if name in ["first_name", "last_name"]:
                # If multiple words still present, take the first token for first_name or last token for last_name
                tokens = clean.split()
                if len(tokens) > 1 and name == "first_name":
                    clean = tokens[0]
                elif len(tokens) > 1 and name == "last_name":
                    clean = tokens[-1]
                clean = clean.capitalize()

            if clean:
                return ExtractedField(field_name=name, raw_value=clean, confidence=0.85, extraction_method="rule")

        return None

    def _llm_extract(self, field: FieldDefinition, utterance: str) -> Optional[ExtractedField]:
        """LLM fallback extraction for ambiguous conversational responses."""
        if not self.llm_service:
            return None

        prompt = (
            f"Extract the value for field '{field.name}' (type: {field.type}) from the customer's utterance:\n"
            f"Customer said: \"{utterance}\"\n\n"
            f"Field description: {field.question}\n"
            f"Valid options/constraints: {field.validation.get('options') or field.validation.get('pattern') or 'standard'}\n"
            f"Respond with only the extracted value, or 'NONE' if no value was stated."
        )

        resp = self.llm_service.generate_chat_response(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        ).strip()

        if not resp or resp.upper() == "NONE":
            return None

        # Clean quotes
        resp = resp.strip("\"' ")
        
        # Type conversion
        val: Any = resp
        if field.type == "number":
            try:
                val = float(re.search(r"\d+(\.\d+)?", resp).group(0))
            except Exception:
                pass
        elif field.type == "boolean":
            val = resp.lower() in ["true", "yes", "1"]

        return ExtractedField(
            field_name=field.name,
            raw_value=val,
            confidence=0.85,
            extraction_method="llm",
        )
