"""
Phase 0 — Audio Pipeline Validation
====================================

Standalone test to prove STT + LLM + TTS APIs work independently.

Pipeline:
    test_audio.wav → STT → transcription → LLM → response → TTS → response.mp3

Requirements:
    - OPENAI_API_KEY in environment or .env file
    - openai Python package

Usage:
    cd cimet-reconnect
    venv\\Scripts\\activate   (Windows)
    python apps/backend/tests/manual/test_voice_pipeline.py
"""

import os
import sys
import time
import tempfile
from pathlib import Path

# Load .env from project root
project_root = Path(__file__).resolve().parents[4]  # cimet-reconnect/
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from openai import OpenAI

# ─── Configuration ───────────────────────────────────────────────────────────
STT_MODEL = "whisper-1"
LLM_MODEL = "gpt-4o"
TTS_MODEL = "gpt-4o-mini-tts"
TTS_VOICE = "sage"

SCRIPT_DIR = Path(__file__).parent
TEST_AUDIO_PATH = SCRIPT_DIR / "test_audio.wav"
OUTPUT_AUDIO_PATH = SCRIPT_DIR / "response.mp3"


def create_test_audio(client: OpenAI) -> Path:
    """Generate a small test audio file using TTS (bootstraps the test)."""
    print("[SETUP] Generating test audio file via TTS...")
    
    test_text = "My postcode is 4000 and I live at 123 George Street, Brisbane."
    
    speech = client.audio.speech.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=test_text,
        instructions="Speak in a natural Australian accent, as a customer answering a phone call.",
    )
    
    with open(str(TEST_AUDIO_PATH), "wb") as f:
        for chunk in speech.iter_bytes():
            f.write(chunk)
    size = TEST_AUDIO_PATH.stat().st_size
    print(f"[SETUP] Test audio saved: {TEST_AUDIO_PATH} ({size:,} bytes)")
    return TEST_AUDIO_PATH


def step_1_stt(client: OpenAI, audio_path: Path) -> str:
    """Stage 1: Speech-to-Text — transcribe the test audio."""
    print(f"\n{'='*60}")
    print("[STAGE 1] STT — Speech-to-Text")
    print(f"{'='*60}")
    print(f"  Model:  {STT_MODEL}")
    print(f"  Input:  {audio_path}")
    
    start = time.time()
    with open(audio_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model=STT_MODEL,
            file=audio_file,
            response_format="text",
        )
    elapsed = time.time() - start
    
    text = transcript.strip() if isinstance(transcript, str) else transcript.text.strip()
    print(f"  Result: \"{text}\"")
    print(f"  Time:   {elapsed:.2f}s")
    return text


def step_2_llm(client: OpenAI, transcription: str) -> str:
    """Stage 2: LLM — generate an agent response to the customer speech."""
    print(f"\n{'='*60}")
    print("[STAGE 2] LLM — Agent Response")
    print(f"{'='*60}")
    print(f"  Model:  {LLM_MODEL}")
    print(f"  Input:  \"{transcription}\"")
    
    system_prompt = (
        "You are a friendly Energy comparison assistant helping a customer complete "
        "their energy comparison journey over the phone. The customer previously started "
        "an energy comparison but didn't finish. You are calling them back to help them "
        "complete it. Be concise, professional, and friendly. "
        "Acknowledge what the customer said and ask the next logical question."
    )
    
    start = time.time()
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcription},
        ],
        max_tokens=200,
        temperature=0.7,
    )
    elapsed = time.time() - start
    
    reply = response.choices[0].message.content.strip()
    print(f"  Result: \"{reply}\"")
    print(f"  Tokens: {response.usage.total_tokens}")
    print(f"  Time:   {elapsed:.2f}s")
    return reply


def step_3_tts(client: OpenAI, text: str) -> Path:
    """Stage 3: TTS — convert the agent response to speech."""
    print(f"\n{'='*60}")
    print("[STAGE 3] TTS — Text-to-Speech")
    print(f"{'='*60}")
    print(f"  Model:  {TTS_MODEL}")
    print(f"  Voice:  {TTS_VOICE}")
    print(f"  Input:  \"{text[:80]}...\"" if len(text) > 80 else f"  Input:  \"{text}\"")
    
    start = time.time()
    speech = client.audio.speech.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=text,
        instructions=(
            "Speak in a warm, professional Australian accent. "
            "Natural tone as a friendly customer service agent on a phone call."
        ),
    )
    
    with open(str(OUTPUT_AUDIO_PATH), "wb") as f:
        for chunk in speech.iter_bytes():
            f.write(chunk)
    elapsed = time.time() - start
    
    size = OUTPUT_AUDIO_PATH.stat().st_size
    print(f"  Output: {OUTPUT_AUDIO_PATH} ({size:,} bytes)")
    print(f"  Time:   {elapsed:.2f}s")
    return OUTPUT_AUDIO_PATH


def verify_output(output_path: Path) -> bool:
    """Verify the output audio file exists and is non-empty."""
    print(f"\n{'='*60}")
    print("[VERIFY] Output Validation")
    print(f"{'='*60}")
    
    exists = output_path.exists()
    size = output_path.stat().st_size if exists else 0
    
    print(f"  File exists: {exists}")
    print(f"  File size:   {size:,} bytes")
    print(f"  Non-empty:   {size > 0}")
    
    return exists and size > 0


def main():
    # Fix Windows console encoding
    import io
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    print("+" + "=" * 60 + "+")
    print("|   CIMET Reconnect - Phase 0: Audio Pipeline Validation   |")
    print("+" + "=" * 60 + "+")
    
    # Check API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n[FAIL] ERROR: OPENAI_API_KEY not found in environment.")
        print("   Set it in .env or export OPENAI_API_KEY=sk-...")
        sys.exit(1)
    
    print(f"\n  API Key: {api_key[:12]}...{api_key[-4:]}")
    print(f"  STT Model: {STT_MODEL}")
    print(f"  LLM Model: {LLM_MODEL}")
    print(f"  TTS Model: {TTS_MODEL}")
    print(f"  TTS Voice: {TTS_VOICE}")
    
    client = OpenAI(api_key=api_key)
    
    # Step 0: Create test audio if it doesn't exist
    if not TEST_AUDIO_PATH.exists():
        create_test_audio(client)
    else:
        print(f"\n[SETUP] Using existing test audio: {TEST_AUDIO_PATH}")
    
    # Step 1: STT
    transcription = step_1_stt(client, TEST_AUDIO_PATH)
    
    # Step 2: LLM
    agent_response = step_2_llm(client, transcription)
    
    # Step 3: TTS
    output_path = step_3_tts(client, agent_response)
    
    # Verify
    success = verify_output(output_path)
    
    print(f"\n{'='*60}")
    if success:
        print("[PASS] PIPELINE VALIDATION PASSED")
        print(f"   Input:  {TEST_AUDIO_PATH}")
        print(f"   Output: {output_path}")
    else:
        print("[FAIL] PIPELINE VALIDATION FAILED")
        sys.exit(1)
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
