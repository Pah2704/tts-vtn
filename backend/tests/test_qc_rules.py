# backend/tests/test_qc_rules.py
from __future__ import annotations
import io
import numpy as np
import soundfile as sf


from typing import Any, Dict, cast
from backend.modules.audio_pipeline import run_pipeline
from backend.modules.quality_control import measure_metrics


def _wav_bytes_from_array(x: np.ndarray, sr: int = 22050) -> bytes:
    bio = io.BytesIO()
    sf.write(bio, x.astype(np.float32, copy=False), sr, subtype="PCM_16", format="WAV")
    return bio.getvalue()


def _toy_speech_with_noise(sr: int = 22050, dur_s: float = 3.0, noise_std: float = 0.05) -> np.ndarray:
    t = np.linspace(0.0, dur_s, int(sr * dur_s), endpoint=False, dtype=np.float32)
    voice = 0.20 * np.sin(2 * np.pi * 200 * t) + 0.05 * np.sin(2 * np.pi * 1000 * t)
    noise = np.random.normal(0.0, noise_std, size=t.shape).astype(np.float32)
    x = voice + noise
    return np.clip(x, -1.0, 1.0)


def test_nr_strong_improves_snr():
    """Preset 'announcement' (NR strong) phải >= SNR preset 'natural_minimal' (NR light)."""
    # Skip nếu không có noisereduce (để tránh false negative)
    try:
        import noisereduce  # noqa: F401
    except Exception:
        import pytest
        pytest.skip("noisereduce not installed; NR bypassed")

    x = _toy_speech_with_noise(noise_std=0.06)
    wav = _wav_bytes_from_array(x)

    # NR nhẹ
    _, m_light = run_pipeline(wav, preset_key="natural_minimal")
    ml: Dict[str, Any] = cast(Dict[str, Any], m_light)
    snr_light = float(ml["snrApprox"])  # runtime luôn có

    # NR mạnh
    _, m_strong = run_pipeline(wav, preset_key="announcement")
    ms: Dict[str, Any] = cast(Dict[str, Any], m_strong)
    snr_strong = float(ms["snrApprox"])

    assert snr_strong >= snr_light + 1.0, f"SNR strong {snr_strong:.2f} <= light {snr_light:.2f}"


def test_score_penalizes_large_lufs_deviation():
    """Tín hiệu rất nhỏ (LUFS rất thấp) → score bị trừ đáng kể."""
    sr = 22050
    t = np.linspace(0.0, 2.0, int(sr * 2.0), endpoint=False, dtype=np.float32)
    x = 0.01 * np.sin(2 * np.pi * 300 * t)  # rất nhỏ → lệch LUFS lớn
    wav = _wav_bytes_from_array(x, sr)
    m = measure_metrics(wav)
    md: Dict[str, Any] = cast(Dict[str, Any], m)   # runtime có thêm trường mở rộng
    score = int(md["qualityScore"])
    assert score < 90, f"Expected penalized score (<90), got {score} with LUFS {md['lufsIntegrated']:.2f}"
