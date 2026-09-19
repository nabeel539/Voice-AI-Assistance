"""
CIMET Reconnect — Audio Codec & Normalizer

Handles bidirectional audio transcoding between Twilio Telephony (G.711 mu-law, 8000 Hz, 8-bit mono)
and the internal audio formats used by STT (Whisper WAV/PCM) and TTS (OpenAI Audio).
"""

import io
import math
import struct
import wave
from typing import Optional

try:
    import audioop
except ImportError:
    audioop = None


# ─── Pure Python G.711 Mu-law Lookup Tables (Fallback / Guaranteed) ───────────

def _build_ulaw_tables():
    """Build mu-law encoding/decoding lookup tables for G.711 standard."""
    BIAS = 0x84
    CLIP = 32635

    # Build decode table (8-bit mu-law byte -> 16-bit signed PCM int)
    decode_table = [0] * 256
    for i in range(256):
        ulaw = ~i & 0xFF
        t = ((ulaw & 0x0F) << 3) + BIAS
        t <<= (ulaw & 0x70) >> 4
        sample = (BIAS - t) if (ulaw & 0x80) else (t - BIAS)
        decode_table[i] = sample

    # Build encode table (16-bit signed PCM -> 8-bit mu-law)
    def linear_to_ulaw_sample(sample: int) -> int:
        sign = 0
        if sample < 0:
            sample = -sample
            sign = 0x80
        if sample > CLIP:
            sample = CLIP
        sample += BIAS
        exponent = 7
        for exp in range(7, -1, -1):
            if sample >= (0x80 << exp):
                exponent = exp
                break
        mantissa = (sample >> (exponent + 3)) & 0x0F
        ulaw = ~(sign | (exponent << 4) | mantissa) & 0xFF
        return ulaw

    return decode_table, linear_to_ulaw_sample


_ULAW_DECODE_TABLE, _LINEAR_TO_ULAW_FN = _build_ulaw_tables()


# ─── Public Codec Functions ───────────────────────────────────────────────────

def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Convert 8-bit G.711 mu-law audio bytes to 16-bit signed little-endian PCM bytes."""
    if not mulaw_bytes:
        return b""
    if audioop is not None:
        try:
            return audioop.ulaw2lin(mulaw_bytes, 2)
        except Exception:
            pass

    # Pure Python fallback
    samples = [_ULAW_DECODE_TABLE[b] for b in mulaw_bytes]
    return struct.pack(f"<{len(samples)}h", *samples)


def pcm16_to_mulaw(pcm16_bytes: bytes) -> bytes:
    """Convert 16-bit signed little-endian PCM bytes to 8-bit G.711 mu-law bytes."""
    if not pcm16_bytes:
        return b""
    if audioop is not None:
        try:
            return audioop.lin2ulaw(pcm16_bytes, 2)
        except Exception:
            pass

    # Pure Python fallback
    num_samples = len(pcm16_bytes) // 2
    samples = struct.unpack(f"<{num_samples}h", pcm16_bytes[:num_samples * 2])
    return bytes(_LINEAR_TO_ULAW_FN(s) for s in samples)


def resample_pcm16(
    pcm16_bytes: bytes,
    in_rate: int,
    out_rate: int,
) -> bytes:
    """Resample 16-bit mono PCM audio between sample rates (e.g. 24000Hz -> 8000Hz)."""
    if in_rate == out_rate or not pcm16_bytes:
        return pcm16_bytes

    if audioop is not None:
        try:
            resampled, _ = audioop.ratecv(pcm16_bytes, 2, 1, in_rate, out_rate, None)
            return resampled
        except Exception:
            pass

    # Pure Python linear interpolation resampler
    num_in = len(pcm16_bytes) // 2
    if num_in == 0:
        return b""
    in_samples = struct.unpack(f"<{num_in}h", pcm16_bytes[:num_in * 2])
    ratio = in_rate / out_rate
    num_out = int(num_in / ratio)
    out_samples = []

    for i in range(num_out):
        src_idx = i * ratio
        idx_floor = int(src_idx)
        idx_ceil = min(idx_floor + 1, num_in - 1)
        weight = src_idx - idx_floor
        val = int(in_samples[idx_floor] * (1.0 - weight) + in_samples[idx_ceil] * weight)
        val = max(-32768, min(32767, val))
        out_samples.append(val)

    return struct.pack(f"<{len(out_samples)}h", *out_samples)


def mulaw_to_wav_bytes(mulaw_bytes: bytes, sample_rate: int = 8000) -> bytes:
    """Decode mu-law audio to standard 16-bit PCM WAV container for STT consumption."""
    pcm16 = mulaw_to_pcm16(mulaw_bytes)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16)
    return buf.getvalue()


def create_silent_mulaw_chunk(duration_seconds: float = 0.02, sample_rate: int = 8000) -> bytes:
    """Generate silent mu-law chunk for padding/keepalive. In G.711 mu-law, 0xFF corresponds to silence."""
    num_bytes = int(duration_seconds * sample_rate)
    return b"\xff" * num_bytes


def split_mulaw_into_frames(mulaw_bytes: bytes, frame_ms: int = 20, sample_rate: int = 8000) -> list[bytes]:
    """Split mu-law audio into standard 20ms frames (160 bytes at 8000Hz) for smooth streaming to Twilio."""
    bytes_per_frame = int(sample_rate * (frame_ms / 1000.0))
    if bytes_per_frame <= 0:
        bytes_per_frame = 160
    return [mulaw_bytes[i:i + bytes_per_frame] for i in range(0, len(mulaw_bytes), bytes_per_frame)]


def calculate_mulaw_energy(mulaw_bytes: bytes) -> float:
    """Calculate Root Mean Square (RMS) energy amplitude of a mu-law audio frame."""
    if not mulaw_bytes:
        return 0.0
    pcm16 = mulaw_to_pcm16(mulaw_bytes)
    if not pcm16:
        return 0.0
    if audioop is not None:
        try:
            return float(audioop.rms(pcm16, 2))
        except Exception:
            pass
    num_samples = len(pcm16) // 2
    if num_samples == 0:
        return 0.0
    samples = struct.unpack(f"<{num_samples}h", pcm16[:num_samples * 2])
    sum_squares = sum(s * s for s in samples)
    return math.sqrt(sum_squares / num_samples)

