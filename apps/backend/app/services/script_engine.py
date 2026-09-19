"""
CIMET Reconnect — Script Engine

Configuration-driven conversation scripts that tell the agent
what to ask, how to validate, and when to escalate.

The script configuration is replaceable when CIMET provides the
actual field list and recovery-call recording.
"""

import json
import re
from pathlib import Path
from typing import Any, Optional

from app.domain.models import FieldDefinition, JourneyStep


class ScriptEngine:
    """Manages conversation scripts and field collection logic.
    
    Loads field definitions from configuration and provides:
    - What field to collect next
    - What question to ask
    - How to validate the answer
    - When to retry vs escalate
    """

    def __init__(self, fields_path: Optional[Path] = None):
        self._fields_path = fields_path or self._default_path()
        self._fields: list[FieldDefinition] = []
        self._load_fields()

    @staticmethod
    def _default_path() -> Path:
        """Default path to energy fields configuration."""
        return Path(__file__).resolve().parents[4] / "data" / "mock" / "energy_fields.json"

    def _load_fields(self) -> None:
        """Load field definitions from JSON configuration."""
        if not self._fields_path.exists():
            raise FileNotFoundError(f"Fields config not found: {self._fields_path}")

        with open(self._fields_path, "r", encoding="utf-8") as f:
            raw_fields = json.load(f)

        self._fields = [FieldDefinition(**field) for field in raw_fields]

    @property
    def all_fields(self) -> list[FieldDefinition]:
        """Get all field definitions."""
        return list(self._fields)

    def get_fields_for_step(self, step: JourneyStep) -> list[FieldDefinition]:
        """Get all fields belonging to a specific journey step."""
        return [f for f in self._fields if f.step == step]

    def get_field(self, field_name: str) -> Optional[FieldDefinition]:
        """Get a specific field definition by name."""
        for field in self._fields:
            if field.name == field_name:
                return field
        return None

    def get_missing_fields(
        self, step: JourneyStep, collected: dict[str, Any]
    ) -> list[FieldDefinition]:
        """Get fields for a step that haven't been collected yet."""
        step_fields = self.get_fields_for_step(step)
        return [f for f in step_fields if f.name not in collected]

    def get_next_field(
        self, step: JourneyStep, collected: dict[str, Any]
    ) -> Optional[FieldDefinition]:
        """Get the next field to collect for a step."""
        missing = self.get_missing_fields(step, collected)
        return missing[0] if missing else None

    def is_step_complete(self, step: JourneyStep, collected: dict[str, Any]) -> bool:
        """Check if all required fields for a step have been collected."""
        required_fields = [f for f in self.get_fields_for_step(step) if f.required]
        return all(f.name in collected for f in required_fields)

    def validate_field(self, field_name: str, value: Any) -> tuple[bool, Optional[str]]:
        """Validate a field value against its definition.
        
        Returns:
            (is_valid, error_message)
        """
        field = self.get_field(field_name)
        if not field:
            return False, f"Unknown field: {field_name}"

        if value is None or (isinstance(value, str) and value.strip() == ""):
            if field.required:
                return False, f"{field_name} is required"
            return True, None

        validation = field.validation
        if not validation:
            return True, None

        str_value = str(value).strip()

        # Pattern validation
        if "pattern" in validation:
            pattern = validation["pattern"]
            if not re.match(pattern, str_value):
                return False, f"Invalid format for {field_name}"

        # Min length
        if "min_length" in validation:
            if len(str_value) < validation["min_length"]:
                return False, f"{field_name} is too short"

        # Allowed values (enum)
        if "allowed_values" in validation:
            allowed = [v.lower() for v in validation["allowed_values"]]
            if str_value.lower() not in allowed:
                return False, f"Invalid value for {field_name}. Expected one of: {', '.join(validation['allowed_values'])}"

        # Min value (numeric)
        if "min_value" in validation:
            try:
                num_value = float(str_value)
                if num_value < validation["min_value"]:
                    return False, f"{field_name} must be at least {validation['min_value']}"
            except ValueError:
                return False, f"{field_name} must be a number"

        return True, None

    def get_all_required_fields(self) -> list[FieldDefinition]:
        """Get all required fields across all steps."""
        return [f for f in self._fields if f.required]

    def get_step_order(self) -> list[JourneyStep]:
        """Get the ordered list of steps based on field definitions."""
        seen = set()
        order = []
        for field in self._fields:
            if field.step not in seen:
                seen.add(field.step)
                order.append(field.step)
        return order
