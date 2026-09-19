"""
CIMET Reconnect — FastAPI Application

AI Voice Agent for Energy Lead Recovery.
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.calls import router as calls_router
from app.api.health import router as health_router
from app.api.leads import router as leads_router
from app.api.telephony import router as telephony_router
from app.api.vapi_webhook import router as vapi_webhook_router
from app.api.voice import router as voice_router
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    settings = get_settings()
    print(f"[STARTUP] CIMET Reconnect Backend")
    print(f"  Environment: {settings.app_env}")
    print(f"  Debug: {settings.app_debug}")
    print(f"  LLM Model: {settings.openai_llm_model}")
    print(f"  STT Model: {settings.openai_stt_model}")
    print(f"  TTS Model: {settings.openai_tts_model}")
    print(f"  Telephony: {settings.telephony_provider}")
    yield
    print("[SHUTDOWN] CIMET Reconnect Backend")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="CIMET Reconnect",
        description="AI Voice Agent for Energy Lead Recovery",
        version="0.1.0",
        debug=settings.app_debug,
        lifespan=lifespan,
    )

    # CORS — allow frontend dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    app.include_router(health_router)
    app.include_router(leads_router)
    app.include_router(calls_router)
    app.include_router(voice_router)
    app.include_router(telephony_router)
    app.include_router(vapi_webhook_router)

    return app


# Application instance
app = create_app()
