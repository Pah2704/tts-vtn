# backend/modules/ducking.py
from __future__ import annotations
from typing import Tuple, Any, cast
import io
import wave
import numpy as np
from pydub import AudioSegment


def _frame_rate(seg: AudioSegment) -> int:
    """Lấy frame rate an toàn (fallback 16000)."""
    try:
        return int(cast(Any, seg).frame_rate)  # type: ignore[attr-defined]
    except Exception:
        return 16000


def _ensure_mono(seg: AudioSegment) -> AudioSegment:
    """Đưa về mono; pydub có set_channels nhưng stub không khai báo."""
    return cast(AudioSegment, cast(Any, seg).set_channels(1))  # type: ignore[attr-defined]


def _resample_to(seg: AudioSegment, sr: int) -> AudioSegment:
    """Đưa về sample rate sr (giữ nguyên sample width/channels)."""
    return cast(AudioSegment, cast(Any, seg).set_frame_rate(sr))  # type: ignore[attr-defined]


def _to_mono_float32(seg: AudioSegment) -> Tuple[np.ndarray, int]:
    """AudioSegment -> (mono float32 [-1,1], sample_rate)."""
    s = _ensure_mono(seg)
    sr = _frame_rate(s)
    # cast Any để Pylance không cảnh báo get_array_of_samples
    samples = np.array(cast(Any, s).get_array_of_samples(), dtype=np.float32)  # type: ignore[attr-defined]

    # scale 16/32-bit -> [-1,1]
    sw = int(getattr(s, "sample_width", 2))
    if sw == 2:
        samples /= 32768.0
    elif sw == 4:
        samples /= 2147483648.0
    else:
        maxv = float(2 ** (8 * sw - 1))
        samples /= maxv
    return samples, sr


def _from_float32(arr: np.ndarray, sr: int) -> AudioSegment:
    """float32 [-1,1] mono -> AudioSegment 16-bit (an toàn cho Pylance)."""
    arr = np.clip(arr, -1.0, 1.0)
    pcm16 = (arr * 32767.0).astype(np.int16)

    # Dùng wave + BytesIO để tránh constructor signature của pydub stubs
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(cast(Any, pcm16).tobytes())
    buf.seek(0)
    return AudioSegment.from_file(buf, format="wav")


def apply_ducking(
    bg: AudioSegment,
    voice: AudioSegment,
    reduction_db: float = 9.0,
    threshold_dbfs: float = -35.0,
    attack_ms: int = 40,
    release_ms: int = 200,
) -> AudioSegment:
    """
    Giảm nền khi có voice vượt ngưỡng:
    - Tạo envelope voice (RMS ngắn) -> gain curve 0 dB hoặc -reduction_db
    - Làm mượt với attack/release -> nhân vào nền.
    """
    # Chuẩn hóa sample rate: lấy sr của voice làm chuẩn
    v_arr, sr = _to_mono_float32(voice)
    bg_resampled = _resample_to(bg, sr)
    b_arr, _ = _to_mono_float32(bg_resampled)

    # Bảo đảm cùng chiều dài
    n = min(len(v_arr), len(b_arr))
    v_arr = v_arr[:n]
    b_arr = b_arr[:n]

    # Envelope RMS khung 10 ms
    win = max(1, int(0.010 * sr))
    pad = win // 2
    v_pad = np.pad(v_arr, (pad, pad), mode="constant")
    kernel = np.ones(win, dtype=np.float32) / float(win)
    v_sq = v_pad * v_pad
    rms = np.sqrt(np.convolve(v_sq, kernel, mode="same"))[:n] + 1e-9

    # Ngưỡng hoạt động (dBFS -> biên độ)
    thr_lin = 10 ** (threshold_dbfs / 20.0)
    active = (rms >= thr_lin).astype(np.float32)

    # Smoother attack/release (one-pole)
    def onepole(x: np.ndarray, ms: int) -> np.ndarray:
        coef = np.exp(-1.0 / max(1, int(ms * sr / 1000)))
        y = np.zeros_like(x, dtype=np.float32)
        for i in range(1, len(x)):
            y[i] = coef * y[i - 1] + (1.0 - coef) * x[i]
        return y

    env_att = onepole(active, attack_ms)
    env_rel = onepole(env_att[::-1], release_ms)[::-1]
    env = np.maximum(env_att, env_rel)

    # Gain curve: 1.0 (0 dB) hoặc 10^(-red/20) khi voice hoạt động
    gain_when_active = 10 ** (-abs(reduction_db) / 20.0)
    gain = (1.0 - env) + env * gain_when_active

    out = b_arr * gain
    return _from_float32(out, sr)
