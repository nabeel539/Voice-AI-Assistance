# Phase 0 — Audio Pipeline Validation

## Purpose

Prove that OpenAI STT + LLM + TTS APIs work independently before building the full CIMET Reconnect application.

## Pipeline

```
test_audio.wav
      ↓
   STT (whisper-1)
      ↓
  "transcribed customer speech"
      ↓
   LLM (gpt-4o)
      ↓
  "AI agent response"
      ↓
   TTS (gpt-4o-mini-tts, voice: sage)
      ↓
  response.mp3
```

## Requirements

- Python 3.11+
- `OPENAI_API_KEY` set in `cimet-reconnect/.env`

## Models Used

| Service | Model | Notes |
|---------|-------|-------|
| STT | `whisper-1` | OpenAI Whisper transcription |
| LLM | `gpt-4o` | Chat completions with system prompt |
| TTS | `gpt-4o-mini-tts` | Voice: `sage`, Australian accent |

## Supported Input Audio

- WAV, MP3, M4A, WEBM, MP4 (any format whisper-1 supports)
- If no test audio exists, the script auto-generates one using TTS

## How to Run

```bash
cd cimet-reconnect
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

pip install openai python-dotenv

python apps/backend/tests/manual/test_voice_pipeline.py
```

## Expected Output

```
╔════════════════════════════════════════════════════════════╗
║   CIMET Reconnect — Phase 0: Audio Pipeline Validation   ║
╚════════════════════════════════════════════════════════════╝

[STAGE 1] STT — Speech-to-Text
  Result: "My postcode is 4000 and I live at 123 George Street, Brisbane."

[STAGE 2] LLM — Agent Response
  Result: "Thank you! I've got your postcode as 4000..."

[STAGE 3] TTS — Text-to-Speech
  Output: response.mp3 (XX,XXX bytes)

✅ PIPELINE VALIDATION PASSED
```

## Output Files

| File | Description |
|------|-------------|
| `test_audio.wav` | Generated test audio (customer speech simulation) |
| `response.mp3` | AI agent voice response |

## Important

- This is a diagnostic/manual integration test
- NOT coupled to the main application architecture
- Do NOT continue to Phase 1 until this pipeline passes
