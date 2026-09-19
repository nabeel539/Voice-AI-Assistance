"""
CIMET Reconnect — Calls & Operator Dashboard API

Endpoints for tracking call state and managing escalated human handoffs.
"""

from typing import List
from fastapi import APIRouter, HTTPException

from app.api.session_store import session_store
from app.domain.call_state import CallState
from app.domain.models import CallStatus
from app.services.handoff_service import HandoffPackage

router = APIRouter(prefix="/api/calls", tags=["calls"])


@router.get("", response_model=List[CallState])
async def list_active_calls():
    """List all currently active call sessions."""
    return session_store.list_calls()


@router.get("/handoffs", response_model=List[HandoffPackage])
async def list_handoffs():
    """List all escalated human handoff packages for the operator console."""
    return session_store.toolbox.handoff_service.get_all_handoffs()


@router.get("/handoffs/{handoff_id}", response_model=HandoffPackage)
async def get_handoff(handoff_id: str):
    """Retrieve a specific handoff package by ID."""
    package = session_store.toolbox.handoff_service.get_handoff(handoff_id)
    if not package:
        raise HTTPException(status_code=404, detail=f"Handoff {handoff_id} not found")
    return package


@router.get("/{call_id}/state", response_model=CallState)
async def get_call_state(call_id: str):
    """Get the complete deterministic state of an ongoing call."""
    call_state = session_store.get_call(call_id)
    if not call_state:
        raise HTTPException(status_code=404, detail=f"Call {call_id} not found")
    return call_state


@router.post("/{call_id}/end", response_model=CallState)
async def end_call(call_id: str):
    """Explicitly terminate an ongoing call."""
    call_state = session_store.get_call(call_id)
    if not call_state:
        raise HTTPException(status_code=404, detail=f"Call {call_id} not found")

    call_state.call_status = CallStatus.ENDED
    return call_state
