"""
CIMET Reconnect — Leads API

Endpoints for querying dropped leads and initiating AI recovery calls.
"""

import base64
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.session_store import session_store
from app.domain.call_state import CallState
from app.domain.models import CallStatus, Lead

router = APIRouter(prefix="/api/leads", tags=["leads"])



class StartCallResponse(BaseModel):
    call_id: str
    lead_id: str
    status: str
    agent_message: str
    audio_base64: Optional[str] = None
    call_state: CallState


@router.get("", response_model=List[Lead])
async def list_leads():
    """Retrieve all available leads from the dataset adapter."""
    return session_store.dataset_adapter.load_leads()


@router.get("/{lead_id}", response_model=Lead)
async def get_lead(lead_id: str):
    """Retrieve details for a single lead."""
    lead = session_store.dataset_adapter.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")
    return lead


@router.post("/{lead_id}/start-call", response_model=StartCallResponse)
async def start_recovery_call(
    lead_id: str,
    generate_voice: bool = Query(default=True, description="Whether to synthesize TTS audio"),
):
    """Initiate an AI recovery call for a dropped lead."""
    lead = session_store.dataset_adapter.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")

    # Create new call state starting from last completed step
    call_state = CallState.from_lead(lead)
    if lead.test_contact:
        call_state.collected_fields["phone"] = lead.test_contact

    # Start the call workflow (DNC check + consent prompt)
    start_result = session_store.agent.start_call(call_state)
    agent_message = start_result.get("agent_message", "")
    call_state.add_message("assistant", agent_message)

    # Only save to active calls and generate voice if DNC verification passes
    if start_result.get("status") != "dnc_blocked":
        session_store.save_call(call_state)
    else:
        call_state.call_status = CallStatus.DECLINED

    audio_base64 = None
    if generate_voice and agent_message and start_result.get("status") != "dnc_blocked":
        try:
            audio_bytes = session_store.tts.synthesize(agent_message)
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        except Exception as e:
            # Fallback gracefully if OpenAI TTS is unavailable or quota limited
            audio_base64 = None


    return StartCallResponse(
        call_id=call_state.call_id,
        lead_id=call_state.lead_id,
        status=start_result.get("status", "active"),
        agent_message=agent_message,
        audio_base64=audio_base64,
        call_state=call_state,
    )
