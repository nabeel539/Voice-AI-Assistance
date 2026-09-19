"""
CIMET Reconnect — Dataset Adapter

Converts external dataset records into internal Lead models.
The adapter pattern allows swapping data sources without rewriting the agent.
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.domain.models import JourneyStep, Lead


class DatasetAdapter(ABC):
    """Abstract interface for loading lead data."""

    @abstractmethod
    def load_leads(self) -> list[Lead]:
        """Load all leads from the data source."""
        ...

    @abstractmethod
    def get_lead(self, lead_id: str) -> Optional[Lead]:
        """Get a specific lead by ID."""
        ...


class MockDatasetAdapter(DatasetAdapter):
    """Loads leads from the mock JSON dataset.
    
    Maps the external dataset shape:
        {"lead_id": "...", "last_completed_step": "...", "test_contact": "..."}
    
    to the internal Lead model.
    """

    def __init__(self, data_path: Optional[Path] = None):
        self._data_path = data_path or self._default_path()
        self._leads: Optional[list[Lead]] = None

    @staticmethod
    def _default_path() -> Path:
        """Default path to mock leads data."""
        return Path(__file__).resolve().parents[4] / "data" / "mock" / "leads.json"

    def _ensure_loaded(self) -> None:
        """Load leads from disk if not already cached."""
        if self._leads is None:
            self._leads = self._load_from_file()

    def _load_from_file(self) -> list[Lead]:
        """Read and parse the JSON file, converting to Lead models."""
        if not self._data_path.exists():
            raise FileNotFoundError(f"Dataset not found: {self._data_path}")

        with open(self._data_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        leads = []
        for record in raw_data:
            lead = self._map_record(record)
            if lead:
                leads.append(lead)

        return leads

    @staticmethod
    def _map_record(record: dict) -> Optional[Lead]:
        """Map an external dataset record to an internal Lead model.
        
        This is the adapter mapping layer — when CIMET provides the real
        dataset, only this method needs to change.
        """
        try:
            # Map external step names to internal JourneyStep enum
            step_str = record.get("last_completed_step", "")
            try:
                step = JourneyStep(step_str)
            except ValueError:
                # Unknown step — default to first step
                step = JourneyStep.PROPERTY_DETAILS

            return Lead(
                lead_id=record["lead_id"],
                last_completed_step=step,
                test_contact=record.get("test_contact", ""),
                phone=record.get("phone") or record.get("test_contact", ""),
                customer_name=record.get("customer_name"),
                first_name=record.get("first_name"),
                last_name=record.get("last_name"),
                email=record.get("email"),
            )
        except (KeyError, ValueError) as e:
            print(f"[WARN] Skipping invalid lead record: {e}")
            return None

    def load_leads(self) -> list[Lead]:
        """Load all leads from the mock dataset."""
        self._ensure_loaded()
        return list(self._leads)  # Return a copy

    def get_lead(self, lead_id: str) -> Optional[Lead]:
        """Get a specific lead by ID."""
        self._ensure_loaded()
        for lead in self._leads:
            if lead.lead_id == lead_id:
                return lead
        return None

    def reload(self) -> None:
        """Force reload from disk (useful after dataset changes)."""
        self._leads = None
        self._ensure_loaded()
