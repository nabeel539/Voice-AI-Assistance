"""
CIMET Reconnect — Voice Processing API

Receives customer voice audio (or text) from the browser or telephony adapter,
transcribes via STT, evaluates safety guardrails, processes LangGraph recovery flow,
and returns synthesized TTS audio response.
"""

import base64
from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.session_store import session_store
from app.domain.call_state import CallState
from app.services.guardrail_service import GuardrailCheckResult, redact_payment_info
from app.services.handoff_service import HandoffPackage
from app.services.journey_service import SubmissionResult

router = APIRouter(prefix="/api/voice", tags=["voice"])


class ProcessTurnTextRequest(BaseModel):
    call_id: str
    text: str
    generate_voice: bool = True
    confidence: float = 1.0


class ProcessTurnResponse(BaseModel):
    call_id: str
    customer_utterance: str
    agent_message: str
    audio_base64: Optional[str] = None
    status: str
    call_state: CallState
    guardrail_result: Optional[GuardrailCheckResult] = None
    handoff_package: Optional[HandoffPackage] = None
    submission_result: Optional[SubmissionResult] = None


@router.post("/process-turn", response_model=ProcessTurnResponse)
async def process_turn(
    call_id: str = Form(...),
    text: Optional[str] = Form(None),
    audio: Optional[UploadFile] = File(None),
    generate_voice: bool = Form(True),
    confidence: Optional[float] = Form(None),
):
    """Process an audio or text conversational turn from the browser or phone adapter."""
    call_state = session_store.get_call(call_id)
    if not call_state:
        raise HTTPException(status_code=404, detail=f"Active call session {call_id} not found")

    customer_utterance = ""
    turn_confidence = 1.0

    # 1. Handle Audio via STT
    if audio is not None:
        audio_bytes = await audio.read()
        if len(audio_bytes) > 0:
            try:
                stt_res = session_store.stt.transcribe(audio_bytes)
                customer_utterance = stt_res.text
                turn_confidence = stt_res.confidence
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Speech transcription failed: {str(e)}")

    # 2. Handle direct text input (fallback / text console mode)
    if not customer_utterance and text:
        customer_utterance = text.strip()
        if confidence is not None:
            turn_confidence = float(confidence)

    if not customer_utterance:
        raise HTTPException(status_code=400, detail="No speech or text provided in turn request")

    # Sanitize user utterance to ensure zero card/payment secrets enter transcript or state
    safe_utterance = redact_payment_info(customer_utterance)

    # Record customer message in conversation history
    call_state.add_message("user", safe_utterance)

    # 3. Process turn through LangGraph recovery agent with STT confidence
    turn_result = session_store.agent.process_turn(
        call_state=call_state,
        customer_utterance=customer_utterance,
        confidence=turn_confidence,
    )
    agent_message = turn_result.get("agent_message", "")
    call_state.add_message("assistant", agent_message)

    # 4. Synthesize agent response via TTS
    audio_base64 = None
    if generate_voice and agent_message:
        try:
            tts_bytes = session_store.tts.synthesize(agent_message)
            audio_base64 = base64.b64encode(tts_bytes).decode("utf-8")
        except Exception as e:
            # Continue gracefully if TTS fails
            audio_base64 = None

    return ProcessTurnResponse(
        call_id=call_state.call_id,
        customer_utterance=safe_utterance,
        agent_message=agent_message,
        audio_base64=audio_base64,
        status=turn_result.get("status", "active"),
        call_state=call_state,
        guardrail_result=turn_result.get("guardrail_result"),
        handoff_package=turn_result.get("handoff_package"),
        submission_result=turn_result.get("submission_result"),
    )



@router.post("/process-turn-json", response_model=ProcessTurnResponse)
async def process_turn_json(request: ProcessTurnTextRequest):
    """JSON version of process turn for headless test automation and fast development."""
    return await process_turn(
        call_id=request.call_id,
        text=request.text,
        audio=None,
        generate_voice=request.generate_voice,
        confidence=request.confidence,
    )

