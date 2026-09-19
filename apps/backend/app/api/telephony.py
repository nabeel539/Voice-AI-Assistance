"""
CIMET Reconnect — Twilio Telephony & Media Stream API

Handles outbound phone calling, Twilio TwiML webhooks, call status tracking,
and real-time bidirectional audio streaming via Twilio Media Streams WebSockets.
"""

import asyncio
import base64
import json
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.api.session_store import session_store
from app.config import get_settings
from app.domain.call_state import CallState
from app.domain.models import CallStatus, ConsentStatus, EscalationReason, Lead
from app.services.audio_codec import calculate_mulaw_energy, mulaw_to_wav_bytes, split_mulaw_into_frames
from app.services.guardrail_service import redact_payment_info
from app.services.telemetry_logger import TelemetryEvent, telemetry_logger

logger = logging.getLogger("cimet.telephony")
router = APIRouter(prefix="/api/telephony", tags=["telephony"])


# ─── Request & Response Models ────────────────────────────────────────────────

class OutboundCallRequest(BaseModel):
    lead_id: str
    phone_number: Optional[str] = None


class OutboundCallResponse(BaseModel):
    call_id: str
    lead_id: str
    twilio_call_sid: Optional[str] = None
    status: str
    call_state: CallState
    message: str


# ─── Outbound Call Initiation (with Mandatory DNC Gate) ───────────────────────

@router.post("/outbound-call", response_model=OutboundCallResponse)
async def initiate_outbound_call(request: OutboundCallRequest, req: Request):
    """Initiate an outbound voice call for a dropped lead with mandatory pre-call DNC check."""
    lead = session_store.dataset_adapter.get_lead(request.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead {request.lead_id} not found")

    settings = get_settings()
    # Dynamic phone resolution: request -> lead.phone -> lead.test_contact -> settings fallback
    target_phone = (
        request.phone_number
        or (getattr(lead, "phone", None) if getattr(lead, "phone", None) else None)
        or lead.test_contact
        or settings.effective_test_recipient_phone
        or ""
    ).strip()
    if not target_phone:
        raise HTTPException(status_code=400, detail=f"No valid phone number for lead {request.lead_id}")

    # 1. Create CallState with active channel
    call_state = CallState.from_lead(lead)
    active_provider = session_store.telephony.provider_name
    call_state.channel = active_provider if active_provider in ("vapi", "twilio") else "twilio"
    call_state.to_phone = target_phone
    call_state.phone = target_phone

    # 2. Mandatory Pre-Call DNC Check (Must execute BEFORE initiating outbound call)
    dnc_result = session_store.toolbox.check_dnc(target_phone)
    call_state.mark_dnc_checked(allowed=dnc_result.allowed)

    if not dnc_result.allowed:
        call_state.call_status = CallStatus.DECLINED
        session_store.save_call(call_state)
        telemetry_logger.log(
            "DNC_BLOCKED",
            f"Blocked outbound call to {target_phone} (registered on DNC list)",
            level="WARNING",
            category="dnc",
            call_id=call_state.call_id,
            to=target_phone,
            lead_id=lead.lead_id,
        )
        logger.warning(f"[DNC_BLOCKED] Outbound call blocked for {target_phone} (Lead: {lead.lead_id})")
        return OutboundCallResponse(
            call_id=call_state.call_id,
            lead_id=lead.lead_id,
            twilio_call_sid=None,
            status="dnc_blocked",
            call_state=call_state,
            message="Phone number is registered on Do-Not-Call registry. Outbound call was not initiated.",
        )

    # 3. Dial out via Active Telephony Service (Vapi / Mock / Twilio)
    try:
        call_context = {
            "last_completed_step": lead.last_completed_step.value if hasattr(lead.last_completed_step, "value") else str(lead.last_completed_step),
            "energy_type": getattr(lead, "energy_type", "electricity"),
        }
        provider_call_id = session_store.telephony.place_outbound_call(
            to_number=target_phone,
            lead_id=lead.lead_id,
            call_id=call_state.call_id,
            context=call_context,
        )
        call_state.twilio_call_sid = provider_call_id
        call_state.call_status = CallStatus.PENDING
        session_store.save_call(call_state)
        session_store.map_twilio_call(provider_call_id, call_state.call_id)

        telemetry_logger.log(
            "OUTBOUND_CALL_PLACED",
            f"Dialing {target_phone} via {active_provider.upper()} (Call ID: {provider_call_id})",
            level="SUCCESS",
            category="telephony",
            call_id=call_state.call_id,
            to_phone=target_phone,
            call_sid=provider_call_id,
            lead_id=lead.lead_id,
        )
        logger.info(f"[{active_provider.upper()}_CALL_PLACED] ID: {provider_call_id} to {target_phone} (Lead: {lead.lead_id})")
        return OutboundCallResponse(
            call_id=call_state.call_id,
            lead_id=lead.lead_id,
            twilio_call_sid=provider_call_id,
            status="initiated",
            call_state=call_state,
            message=f"Outbound call initiated via {active_provider.upper()} (Call ID: {provider_call_id}).",
        )
    except Exception as e:
        call_state.call_status = CallStatus.FAILED
        session_store.save_call(call_state)
        telemetry_logger.log(
            "OUTBOUND_CALL_FAILED",
            f"Failed dialing {target_phone} via {active_provider.upper()}: {str(e)}",
            level="ERROR",
            category="telephony",
            call_id=call_state.call_id,
            error=str(e),
        )
        logger.error(f"[{active_provider.upper()}_CALL_ERROR] Failed to initiate call to {target_phone}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"{active_provider.upper()} call initiation failed: {str(e)}")


# ─── Twilio TwiML Voice Webhook ───────────────────────────────────────────────

@router.api_route("/voice-webhook", methods=["GET", "POST"])
async def voice_webhook(
    request: Request,
    call_id: Optional[str] = Query(None),
):
    """Twilio voice webhook triggered when call is answered. Returns TwiML connecting to Media Stream."""
    # Twilio posts form-data with CallSid, From, To, etc.
    form_data = {}
    if request.method == "POST":
        try:
            form_data = dict(await request.form())
        except Exception:
            pass

    call_sid = form_data.get("CallSid")
    resolved_call_id = call_id or form_data.get("call_id")

    call_state = None
    if resolved_call_id:
        call_state = session_store.get_call(resolved_call_id)
    if not call_state and call_sid:
        call_state = session_store.get_call_by_twilio_sid(call_sid)

    if call_state and call_sid:
        call_state.twilio_call_sid = call_sid
        session_store.map_twilio_call(call_sid, call_state.call_id)

    # Determine WebSocket streaming URL (wss:// for ngrok/public or ws:// for local)
    settings = get_settings()
    if settings.twilio_webhook_base_url:
        base = settings.twilio_webhook_base_url.rstrip("/")
        if base.startswith("https://"):
            stream_base = "wss://" + base[len("https://"):]
        elif base.startswith("http://"):
            stream_base = "ws://" + base[len("http://"):]
        else:
            stream_base = f"wss://{base}"
        stream_param = f"?call_id={call_state.call_id}" if call_state else ""
        stream_ws_url = f"{stream_base}/api/telephony/media-stream{stream_param}"
    else:
        forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost:8000")
        forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        ws_protocol = "wss" if (forwarded_proto == "https" or "localhost" not in forwarded_host) else "ws"
        stream_param = f"?call_id={call_state.call_id}" if call_state else ""
        stream_ws_url = f"{ws_protocol}://{forwarded_host}/api/telephony/media-stream{stream_param}"

    twiml_xml = session_store.telephony.generate_media_stream_twiml(
        call_id=call_state.call_id if call_state else "",
        stream_ws_url=stream_ws_url,
    )
    telemetry_logger.log(
        "VOICE_WEBHOOK_ANSWERED",
        f"Twilio call answered (SID: {call_sid}) -> Connected to Media Stream: {stream_ws_url}",
        level="SUCCESS",
        category="telephony",
        call_id=call_state.call_id if call_state else None,
        call_sid=call_sid,
        stream_ws_url=stream_ws_url,
        twiml=twiml_xml,
    )
    logger.info(f"[VOICE_WEBHOOK] Returning TwiML: {twiml_xml}")
    return Response(content=twiml_xml, media_type="application/xml")


# ─── Twilio Status Callback ───────────────────────────────────────────────────

@router.post("/status-callback")
async def status_callback(
    request: Request,
    call_id: Optional[str] = Query(None),
):
    """Receives status updates from Twilio (initiated, ringing, answered, completed, busy, no-answer)."""
    form_data = {}
    try:
        form_data = dict(await request.form())
    except Exception:
        pass

    call_sid = form_data.get("CallSid")
    call_status_str = (form_data.get("CallStatus") or "").lower()

    call_state = None
    if call_id:
        call_state = session_store.get_call(call_id)
    if not call_state and call_sid:
        call_state = session_store.get_call_by_twilio_sid(call_sid)

    if call_state:
        if call_status_str in ("in-progress", "answered"):
            if call_state.call_status == CallStatus.PENDING:
                call_state.call_status = CallStatus.IN_PROGRESS
        elif call_status_str in ("completed", "canceled"):
            if call_state.call_status in (CallStatus.PENDING, CallStatus.IN_PROGRESS):
                call_state.call_status = CallStatus.ENDED
        elif call_status_str in ("busy", "failed", "no-answer"):
            call_state.call_status = CallStatus.FAILED

        telemetry_logger.log(
            "TWILIO_STATUS_UPDATE",
            f"Twilio Status: {call_status_str.upper()} (Internal Call State: {call_state.call_status.value})",
            level="INFO",
            category="telephony",
            call_id=call_state.call_id,
            call_sid=call_sid,
            call_status=call_status_str,
        )
        logger.info(f"[TWILIO_STATUS] SID: {call_sid} -> {call_status_str} (State: {call_state.call_status.value})")

    return {"status": "ok"}


# ─── Real-Time Twilio Media Stream WebSocket ──────────────────────────────────

@router.websocket("/media-stream")
async def twilio_media_stream_websocket(
    websocket: WebSocket,
    call_id: Optional[str] = Query(None),
):
    """Full-duplex real-time audio WebSocket connecting Twilio phone audio to STT -> LangGraph Agent -> TTS."""
    await websocket.accept()
    logger.info(f"[TWILIO_WS_CONNECTED] WebSocket established (call_id param: {call_id})")
    telemetry_logger.log(
        "WS_CONNECTED",
        f"Twilio Media Stream WebSocket accepted (call_id param: {call_id})",
        level="SUCCESS",
        category="telephony",
        call_id=call_id,
    )

    stream_sid: Optional[str] = None
    call_sid: Optional[str] = None
    call_state: Optional[CallState] = None
    inbound_audio_buffer = bytearray()
    is_agent_speaking = False
    stop_current_agent_playback = False
    ws_send_lock = asyncio.Lock()

    # VAD & Speech State
    is_speech_active = False
    consecutive_speech_frames = 0
    consecutive_silence_frames = 0
    max_energy_in_utterance = 0.0
    SPEECH_RMS_THRESHOLD = 700.0
    SILENCE_RMS_THRESHOLD = 450.0
    BARGE_IN_RMS_THRESHOLD = 1300.0
    barge_in_consecutive_count = 0
    barge_in_triggered_for_turn = False

    # Known Whisper silence / ambient noise hallucinations to filter out
    SILENCE_HALLUCINATIONS = {
        "thank you.", "thank you", "thank you very much.", "thanks for watching.",
        "thanks for watching", "you", "bye", "bye.", "subtitles by", "subtitles",
        "subscribe", "thank you for watching.", "silence", "...", ".", ""
    }

    async def safe_send_text(msg_dict: dict) -> bool:
        """Safely serialize and send JSON message over WebSocket."""
        try:
            async with ws_send_lock:
                await websocket.send_text(json.dumps(msg_dict))
            return True
        except Exception:
            return False

    async def send_mulaw_to_twilio(mulaw_bytes: bytes, current_stream_sid: str):
        """Stream 8kHz mu-law audio to Twilio in 20ms chunks."""
        nonlocal is_agent_speaking, stop_current_agent_playback, barge_in_triggered_for_turn
        is_agent_speaking = True
        stop_current_agent_playback = False
        barge_in_triggered_for_turn = False

        frames = split_mulaw_into_frames(mulaw_bytes, frame_ms=20, sample_rate=8000)
        for frame in frames:
            if stop_current_agent_playback:
                logger.info(f"[BARGE_IN_TRIGGERED] Halting agent playback on stream {current_stream_sid}")
                break
            payload = base64.b64encode(frame).decode("utf-8")
            media_msg = {
                "event": "media",
                "streamSid": current_stream_sid,
                "media": {
                    "payload": payload,
                },
            }
            sent = await safe_send_text(media_msg)
            if not sent:
                break
            # 20ms frame pacing
            await asyncio.sleep(0.018)

        # Agent finished speaking -> flush any echo residual & add small pause
        await asyncio.sleep(0.25)
        inbound_audio_buffer.clear()
        is_speech_active = False
        consecutive_speech_frames = 0
        consecutive_silence_frames = 0
        is_agent_speaking = False

    try:
        while True:
            raw_text = await websocket.receive_text()
            data = json.loads(raw_text)
            event_type = data.get("event")

            # ── 1. Stream Connected & Start Event ─────────────────────────────
            if event_type == "start":
                start_data = data.get("start", {})
                stream_sid = start_data.get("streamSid")
                call_sid = start_data.get("callSid")
                custom_params = start_data.get("customParameters", {})
                resolved_id = custom_params.get("call_id") or call_id

                if resolved_id:
                    call_state = session_store.get_call(resolved_id)
                if not call_state and call_sid:
                    call_state = session_store.get_call_by_twilio_sid(call_sid)

                logger.info(f"[TWILIO_STREAM_START] StreamSid: {stream_sid}, CallSid: {call_sid}, CallId: {resolved_id}")
                telemetry_logger.log(
                    "STREAM_START",
                    f"Twilio stream started: StreamSid={stream_sid}, CallSid={call_sid}, resolved_call_id={resolved_id}, call_state_found={call_state is not None}",
                    level="INFO",
                    category="telephony",
                    call_id=resolved_id,
                    stream_sid=stream_sid,
                    call_sid_from_stream=call_sid,
                    call_state_found=call_state is not None,
                )

                if call_state:
                    call_state.twilio_stream_sid = stream_sid
                    if call_sid:
                        call_state.twilio_call_sid = call_sid
                        session_store.map_twilio_call(call_sid, call_state.call_id)

                    # Start call recovery flow & generate mandatory recording disclosure / consent prompt
                    try:
                        start_res = session_store.agent.start_call(call_state)
                        greeting_text = start_res.get("agent_message", "")
                        call_state.add_message("assistant", greeting_text)

                        telemetry_logger.log(
                            "AGENT_OPENING_PROMPT",
                            f"Emma: \"{greeting_text[:100]}...\"",
                            level="SPEECH",
                            category="agent",
                            call_id=call_state.call_id,
                            stream_sid=stream_sid,
                            greeting_length=len(greeting_text),
                        )
                    except Exception as e:
                        logger.error(f"[AGENT_START_ERROR] Failed starting agent: {e}", exc_info=True)
                        greeting_text = ""

                    # Synthesize opening disclosure & stream to customer phone
                    if greeting_text and stream_sid:
                        try:
                            telemetry_logger.log(
                                "TTS_SYNTHESIZING",
                                f"Synthesizing greeting ({len(greeting_text)} chars) for stream {stream_sid}",
                                level="INFO",
                                category="tts",
                                call_id=call_state.call_id,
                            )
                            mulaw_audio = session_store.tts.synthesize_mulaw(greeting_text)
                            telemetry_logger.log(
                                "TTS_COMPLETE",
                                f"TTS generated {len(mulaw_audio)} bytes of mu-law audio",
                                level="SUCCESS",
                                category="tts",
                                call_id=call_state.call_id,
                                audio_bytes=len(mulaw_audio),
                            )
                            asyncio.create_task(send_mulaw_to_twilio(mulaw_audio, stream_sid))
                        except Exception as e:
                            logger.error(f"[TTS_ERROR] Failed synthesizing opening prompt: {e}", exc_info=True)

            # ── 2. Inbound Audio Media Chunks (VAD & Utterance Processing) ─────
            elif event_type == "media":
                media_data = data.get("media", {})
                chunk_payload = media_data.get("payload", "")
                if chunk_payload and stream_sid and call_state:
                    chunk_bytes = base64.b64decode(chunk_payload)
                    frame_energy = calculate_mulaw_energy(chunk_bytes)

                    # 1. Debounced Barge-In Detection (Caller interrupts while Emma is speaking)
                    if is_agent_speaking:
                        if frame_energy >= BARGE_IN_RMS_THRESHOLD:
                            barge_in_consecutive_count += 1
                        else:
                            barge_in_consecutive_count = max(0, barge_in_consecutive_count - 1)

                        # Require at least 4 consecutive loud frames (80ms) of sustained speech
                        if barge_in_consecutive_count >= 4 and not barge_in_triggered_for_turn:
                            stop_current_agent_playback = True
                            barge_in_triggered_for_turn = True
                            barge_in_consecutive_count = 0
                            clear_msg = {"event": "clear", "streamSid": stream_sid}
                            await safe_send_text(clear_msg)
                            telemetry_logger.log(
                                "BARGE_IN_TRIGGERED",
                                f"Customer interruption detected on stream {stream_sid} -> playback halted & Twilio clear event sent",
                                level="WARNING",
                                category="telephony",
                                call_id=call_state.call_id,
                                stream_sid=stream_sid,
                            )
                            logger.info(f"[BARGE_IN] Sent clear event to Twilio stream {stream_sid}")
                        # CRITICAL: Do NOT buffer incoming audio while agent is speaking to prevent self-echo loops
                        continue

                    # Guard: If call already reached terminal status (handoff/declined/ended), do not loop
                    if call_state.call_status in (CallStatus.HANDOFF, CallStatus.DECLINED, CallStatus.ENDED):
                        continue

                    # 2. Voice Activity Detection (VAD)
                    if frame_energy >= SPEECH_RMS_THRESHOLD:
                        consecutive_speech_frames += 1
                        consecutive_silence_frames = 0
                        max_energy_in_utterance = max(max_energy_in_utterance, frame_energy)
                        if consecutive_speech_frames >= 3:  # 60ms of speech
                            is_speech_active = True
                    else:
                        consecutive_silence_frames += 1
                        if consecutive_silence_frames > 2:
                            consecutive_speech_frames = 0

                    # 3. Buffer Inbound Audio
                    inbound_audio_buffer.extend(chunk_bytes)

                    # 4. Check End of Utterance:
                    # User was speaking and now paused for >= 700ms (35 frames) OR buffer >= 4.5s (36000 bytes)
                    should_process_turn = (
                        is_speech_active
                        and (consecutive_silence_frames >= 35 or len(inbound_audio_buffer) >= 36000)
                    )

                    # If silence without prior speech exceeds 8000 bytes (1s), prune to prevent infinite buildup
                    if not is_speech_active and len(inbound_audio_buffer) > 8000:
                        inbound_audio_buffer = inbound_audio_buffer[-3200:]  # Keep last 200ms lead-in

                    if should_process_turn:
                        audio_to_process = bytes(inbound_audio_buffer)
                        utterance_peak_energy = max_energy_in_utterance

                        # Reset VAD state for next turn
                        inbound_audio_buffer.clear()
                        is_speech_active = False
                        consecutive_speech_frames = 0
                        consecutive_silence_frames = 0
                        max_energy_in_utterance = 0.0

                        # Minimum audio length check (at least 200ms = 1600 bytes)
                        if len(audio_to_process) >= 1600:
                            wav_bytes = mulaw_to_wav_bytes(audio_to_process, sample_rate=8000)

                            customer_utterance = ""
                            turn_confidence = 1.0
                            try:
                                stt_res = session_store.stt.transcribe(wav_bytes)
                                customer_utterance = (stt_res.text or "").strip()
                                turn_confidence = stt_res.confidence
                            except Exception as e:
                                logger.warning(f"[STT_ERROR] Speech transcription failed: {e}")

                            # Filter Whisper silence artifacts
                            cleaned_lower = customer_utterance.lower().strip()
                            is_hallucination = cleaned_lower in SILENCE_HALLUCINATIONS and utterance_peak_energy < 850.0

                            if customer_utterance and len(customer_utterance) > 1 and not is_hallucination:
                                telemetry_logger.log(
                                    "CUSTOMER_SPEECH",
                                    f"Customer: \"{customer_utterance}\" (Confidence: {turn_confidence:.2f})",
                                    level="SPEECH",
                                    category="stt",
                                    call_id=call_state.call_id,
                                    confidence=turn_confidence,
                                )
                                logger.info(f"[PHONE_CUSTOMER_SPOKE] \"{customer_utterance}\" (conf: {turn_confidence:.2f})")
                                safe_utterance = redact_payment_info(customer_utterance)
                                call_state.add_message("user", safe_utterance)

                                # Process turn through LangGraph recovery agent
                                turn_result = session_store.agent.process_turn(
                                    call_state=call_state,
                                    customer_utterance=customer_utterance,
                                    confidence=turn_confidence,
                                )
                                agent_message = turn_result.get("agent_message", "")
                                call_state.add_message("assistant", agent_message)
                                telemetry_logger.log(
                                    "AGENT_REPLY",
                                    f"Emma: \"{agent_message}\" (Status: {turn_result.get('status')})",
                                    level="SPEECH",
                                    category="agent",
                                    call_id=call_state.call_id,
                                    turn_status=turn_result.get("status"),
                                    current_step=call_state.current_step.value if hasattr(call_state.current_step, 'value') else call_state.current_step,
                                    current_field=call_state.current_field,
                                )
                                logger.info(f"[PHONE_AGENT_REPLY] \"{agent_message}\" (Status: {turn_result.get('status')})")

                                # Synthesize agent response into mu-law and stream to phone
                                if agent_message and stream_sid:
                                    try:
                                        response_mulaw = session_store.tts.synthesize_mulaw(agent_message)
                                        turn_status = turn_result.get("status")
                                        if turn_status in ("completed", "submitted", "handed_off", "declined", "dnc_blocked"):
                                            async def stream_closing_and_hangup(mulaw_data: bytes, s_sid: str, c_sid: Optional[str], status_name: str):
                                                await send_mulaw_to_twilio(mulaw_data, s_sid)
                                                await asyncio.sleep(2.0)
                                                if c_sid:
                                                    try:
                                                        session_store.telephony.end_call(c_sid)
                                                        logger.info(f"[CALL_AUTO_TERMINATED] Terminated Twilio call {c_sid} after terminal status '{status_name}'")
                                                        telemetry_logger.log(
                                                            "CALL_TERMINATED",
                                                            f"Call {c_sid} automatically ended cleanly after final message ({status_name})",
                                                            level="SUCCESS",
                                                            category="telephony",
                                                            call_id=call_state.call_id if call_state else None,
                                                            call_sid=c_sid,
                                                            turn_status=status_name,
                                                        )
                                                    except Exception as err:
                                                        logger.warning(f"[CALL_TERMINATION_ERROR] Could not end call {c_sid}: {err}")
                                                if call_state:
                                                    call_state.call_status = CallStatus.ENDED

                                            target_sid = call_sid or (call_state.twilio_call_sid if call_state else None)
                                            asyncio.create_task(stream_closing_and_hangup(response_mulaw, stream_sid, target_sid, turn_status))
                                        else:
                                            asyncio.create_task(send_mulaw_to_twilio(response_mulaw, stream_sid))
                                    except Exception as e:
                                        logger.error(f"[TTS_ERROR] Failed synthesizing reply: {e}")

            # ── 3. Stream Stop Event ──────────────────────────────────────────
            elif event_type == "stop":
                telemetry_logger.log(
                    "MEDIA_STREAM_STOP",
                    f"Twilio Media Stream {stream_sid} disconnected",
                    category="telephony",
                    call_id=call_state.call_id if call_state else None,
                )
                logger.info(f"[TWILIO_STREAM_STOP] Stream {stream_sid} stopped")
                if call_state and call_state.call_status in (CallStatus.PENDING, CallStatus.IN_PROGRESS):
                    call_state.call_status = CallStatus.ENDED
                break

    except WebSocketDisconnect:
        logger.info(f"[TWILIO_WS_DISCONNECTED] WebSocket disconnected for stream {stream_sid}")
        telemetry_logger.log(
            "WS_DISCONNECTED",
            f"WebSocket disconnected for stream {stream_sid}",
            level="WARNING",
            category="telephony",
            call_id=call_state.call_id if call_state else call_id,
            stream_sid=stream_sid,
        )
    except Exception as e:
        logger.error(f"[TWILIO_WS_EXCEPTION] Error in media stream: {str(e)}", exc_info=True)
        telemetry_logger.log(
            "WS_EXCEPTION",
            f"WebSocket exception: {e}",
            level="ERROR",
            category="telephony",
            call_id=call_state.call_id if call_state else call_id,
            stream_sid=stream_sid,
            error=str(e),
        )
    finally:
        if call_state and call_state.call_status in (CallStatus.PENDING, CallStatus.IN_PROGRESS):
            call_state.call_status = CallStatus.ENDED


# ─── Synchronous Test Simulation Endpoint ─────────────────────────────────────

class SimulatePhoneTurnRequest(BaseModel):
    call_id: str
    customer_speech_text: str
    confidence: float = 1.0


@router.post("/simulate-phone-turn")
async def simulate_phone_turn(req: SimulatePhoneTurnRequest):
    """Directly simulate a phone conversational turn through the telephony-mapped agent core for testing."""
    call_state = session_store.get_call(req.call_id)
    if not call_state:
        raise HTTPException(status_code=404, detail=f"Call {req.call_id} not found")

    safe_utterance = redact_payment_info(req.customer_speech_text)
    call_state.add_message("user", safe_utterance)

    turn_result = session_store.agent.process_turn(
        call_state=call_state,
        customer_utterance=req.customer_speech_text,
        confidence=req.confidence,
    )
    agent_message = turn_result.get("agent_message", "")
    call_state.add_message("assistant", agent_message)

    # Generate 8kHz mu-law audio
    mulaw_bytes = session_store.tts.synthesize_mulaw(agent_message)
    mulaw_b64 = base64.b64encode(mulaw_bytes).decode("utf-8")

    return {
        "call_id": call_state.call_id,
        "customer_utterance": safe_utterance,
        "agent_message": agent_message,
        "mulaw_base64": mulaw_b64,
        "status": turn_result.get("status", "active"),
        "call_state": call_state,
        "guardrail_result": turn_result.get("guardrail_result"),
        "handoff_package": turn_result.get("handoff_package"),
        "submission_result": turn_result.get("submission_result"),
    }


# ─── Live Telephony & Test Diagnostic Logs ───────────────────────────────────

@router.get("/logs", response_model=list[TelemetryEvent])
async def get_telemetry_logs(
    call_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Retrieve structured real-time telemetry and testing logs for phone and frontend testing."""
    return telemetry_logger.get_events(call_id=call_id, limit=limit)


@router.post("/logs/clear")
async def clear_telemetry_logs():
    """Clear in-memory telemetry logs."""
    telemetry_logger.clear()
    return {"status": "cleared"}
