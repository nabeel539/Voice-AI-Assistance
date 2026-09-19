"""
Unit tests for Audio Codec and Transcoding between G.711 Mu-law and PCM/WAV.
"""

import struct
import wave
import io
import pytest

from app.services.audio_codec import (
    mulaw_to_pcm16,
    pcm16_to_mulaw,
    resample_pcm16,
    mulaw_to_wav_bytes,
    create_silent_mulaw_chunk,
    split_mulaw_into_frames,
)


def test_mulaw_pcm16_roundtrip():
    """Verify mu-law <-> PCM16 conversion retains signal integrity."""
    # Test values
    original_samples = [0, 100, -100, 1000, -1000, 16000, -16000]
    pcm_bytes = struct.pack(f"<{len(original_samples)}h", *original_samples)

    # Encode to mu-law
    mulaw = pcm16_to_mulaw(pcm_bytes)
    assert len(mulaw) == len(original_samples)

    # Decode back to PCM16
    decoded_pcm = mulaw_to_pcm16(mulaw)
    assert len(decoded_pcm) == len(pcm_bytes)

    # In G.711 companding, decoded values are close approximations
    decoded_samples = struct.unpack(f"<{len(original_samples)}h", decoded_pcm)
    for orig, dec in zip(original_samples, decoded_samples):
        assert abs(orig - dec) <= max(abs(orig) * 0.1, 32)


def test_resample_pcm16():
    """Verify resampling downsamples 24kHz to 8kHz by ratio of 3:1."""
    # 2400 samples at 24kHz = 0.1s
    samples_24k = [int(1000 * (i % 10)) for i in range(2400)]
    pcm24k = struct.pack(f"<{len(samples_24k)}h", *samples_24k)

    pcm8k = resample_pcm16(pcm24k, in_rate=24000, out_rate=8000)
    # Expected: 800 samples = 1600 bytes
    assert len(pcm8k) == 800 * 2


def test_mulaw_to_wav_bytes():
    """Verify generated WAV header is valid and parseable by standard wave module."""
    # 1 second of 8kHz mu-law audio = 8000 bytes
    mulaw_audio = b"\xff" * 8000
    wav_bytes = mulaw_to_wav_bytes(mulaw_audio, sample_rate=8000)

    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2  # 16-bit
        assert wf.getframerate() == 8000
        assert wf.getnframes() == 8000


def test_split_mulaw_into_frames():
    """Verify splitting audio into 20ms frames (160 bytes at 8kHz)."""
    # 800 bytes = 5 frames of 160 bytes
    audio = b"\x00" * 800
    frames = split_mulaw_into_frames(audio, frame_ms=20, sample_rate=8000)
    assert len(frames) == 5
    for frame in frames:
        assert len(frame) == 160


def test_create_silent_mulaw_chunk():
    """Verify silent chunk generation."""
    chunk = create_silent_mulaw_chunk(duration_seconds=0.02, sample_rate=8000)
    assert len(chunk) == 160
    assert chunk == b"\xff" * 160
