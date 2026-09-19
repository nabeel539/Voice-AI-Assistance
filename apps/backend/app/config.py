"""
CIMET Reconnect — Application Configuration

Typed configuration loaded from environment variables using Pydantic Settings.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Application & Validation Rules ---
    app_env: str = "development"
    app_debug: bool = True
    log_level: str = "INFO"
    max_validation_retries: int = 2

    # --- OpenAI ---
    openai_api_key: str = ""
    openai_llm_model: str = "gpt-4o"
    openai_stt_model: str = "whisper-1"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "sage"

    # --- Database ---
    database_url: str = "sqlite:///./cimet_reconnect.db"

    # --- CIMET Journey Sandbox ---
    cimet_journey_base_url: str = ""
    cimet_journey_api_key: str = ""

    # --- DNC Provider ---
    dnc_provider: str = "mock"
    dnc_api_url: str = ""
    dnc_api_key: str = ""

    # --- Telephony / Voice Provider ---
    telephony_provider: str = "twilio"  # "twilio" | "vapi" | "mock"
    telephony_simulate: bool = False

    # Vapi explicit settings
    vapi_api_key: str = ""
    vapi_assistant_id: str = ""
    vapi_phone_number_id: str = ""
    vapi_server_url: str = ""
    vapi_webhook_secret: str = ""
    vapi_test_recipient_phone: str = "+917894526165"

    # Twilio active settings
    telephony_account_id: str = ""
    telephony_auth_token: str = ""
    telephony_phone_number: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_api_key_sid: str = ""
    twilio_api_key_secret: str = ""
    twilio_phone_number: str = ""
    twilio_webhook_base_url: str = ""
    twilio_simulate: bool = False
    twilio_test_recipient_phone: str = "+917894526165"
    to_phone_number: str = ""

    @property
    def effective_twilio_account_sid(self) -> str:
        return self.twilio_account_sid or self.telephony_account_id

    @property
    def effective_twilio_auth_token(self) -> str:
        return self.twilio_auth_token or self.telephony_auth_token

    @property
    def effective_twilio_phone_number(self) -> str:
        return self.twilio_phone_number or self.telephony_phone_number

    @property
    def effective_test_recipient_phone(self) -> str:
        return self.to_phone_number or self.twilio_test_recipient_phone or "+917894526165"


    # --- LangSmith Tracing ---
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "cimet-reconnect"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # --- JWT ---
    jwt_secret_key: str = "cimet-reconnect-dev-secret-key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # --- Paths ---
    @property
    def project_root(self) -> Path:
        """Return the project root directory (cimet-reconnect/)."""
        return Path(__file__).resolve().parents[3]

    @property
    def data_dir(self) -> Path:
        """Return the data directory."""
        return self.project_root / "data"

    @property
    def mock_data_dir(self) -> Path:
        """Return the mock data directory."""
        return self.data_dir / "mock"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
