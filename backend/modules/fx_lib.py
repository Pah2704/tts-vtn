# backend/modules/fx_lib.py
from __future__ import annotations
from typing import Optional, Any, cast
from pathlib import Path
import math
import io
import wave
import numpy as np
from pydub import AudioSegment

# Mặc định tìm assets ở backend/assets/fx/<kind>.wav
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fx"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_KINDS = {"none", "rain", "cafe", "forest", "ocean", "fire", "wind"}


def _silence_ms(ms: int, frame_rate: int = 16000) -> AudioSegment:
    """Tạo AudioSegment im lặng an toàn."""
    if hasattr(AudioSegment, "silent"):
        return AudioSegment.silent(duration=ms, frame_rate=frame_rate)  # type: ignore[attr-defined]
    num_samples = max(0, int(ms * frame_rate / 1000))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)       # 16-bit
        wf.setframerate(frame_rate)
        wf.writeframes(b"\x00\x00" * num_samples)
    buf.seek(0)
    return AudioSegment.from_file(buf, format="wav")


def _len_ms(seg: AudioSegment) -> int:
    """Lấy độ dài (ms) — dùng len() qua cast để Pylance không báo."""
    try:
        return int(len(cast(Any, seg)))
    except Exception:
        try:
            frames = cast(Any, seg).frame_count()  # type: ignore[attr-defined]
            sr = cast(Any, seg).frame_rate         # type: ignore[attr-defined]
            return int(frames * 1000.0 / float(sr))
        except Exception:
            return 1


def _frame_rate(seg: AudioSegment) -> int:
    """Lấy frame rate; fallback 16000 nếu stub không expose."""
    try:
        return int(cast(Any, seg).frame_rate)  # type: ignore[attr-defined]
    except Exception:
        return 16000


def load_fx(kind: str) -> AudioSegment:
    """Tải hiệu ứng nền theo kind; nếu không có file thì trả về im lặng 1s."""
    k = (kind or "none").lower()
    if k not in ALLOWED_KINDS:
        k = "none"
    path = ASSETS_DIR / f"{k}.wav"
    if path.exists() and path.is_file():
        return AudioSegment.from_file(str(path), format="wav")
    # fallback: im lặng 1s để pipeline không vấp
    return _silence_ms(1000, frame_rate=16000)


def loop_to_length(seg: AudioSegment, target_ms: int) -> AudioSegment:
    """Lặp seg cho tới target_ms rồi cắt đúng chiều dài (ms)."""
    if target_ms <= 0:
        return _silence_ms(0, frame_rate=_frame_rate(seg))

    seg_ms = max(1, _len_ms(seg))
    times = max(1, int(math.ceil(target_ms / seg_ms)))

    # Pylance không biết operator * của AudioSegment → cast sang Any
    ret_any: Any = seg
    for _ in range(times - 1):
        ret_any = ret_any + seg  # type: ignore[operator]
    out_seg = cast(AudioSegment, ret_any)

    # đảm bảo đủ dài
    if _len_ms(out_seg) < target_ms:
        ret_any = ret_any + seg  # type: ignore[operator]
        out_seg = cast(AudioSegment, ret_any)

    # slicing theo ms — cast Any để Pylance không cảnh báo
    return cast(Any, out_seg)[: int(target_ms)]


def apply_gain_linear(seg: AudioSegment, gain_linear: Optional[float]) -> AudioSegment:
    """
    gain_linear: 0.0 .. 0.5 (None => giữ nguyên). 0.0 => -120 dB ~ tắt nền.
    """
    if gain_linear is None:
        return seg
    g = float(gain_linear)
    if g <= 0.0:
        return seg.apply_gain(-120.0)  # type: ignore[attr-defined]
    if g >= 1.0:
        return seg
    gain_db = 20.0 * math.log10(g)
    return seg.apply_gain(gain_db)  # type: ignore[attr-defined]


def apply_fades(seg: AudioSegment, fade_in_ms: Optional[int], fade_out_ms: Optional[int]) -> AudioSegment:
    if fade_in_ms and fade_in_ms > 0:
        seg = seg.fade_in(int(fade_in_ms))    # type: ignore[attr-defined]
    if fade_out_ms and fade_out_ms > 0:
        seg = seg.fade_out(int(fade_out_ms))  # type: ignore[attr-defined]
    return seg


def make_noise_ms(ms: int, frame_rate: int = 16000, level_db: float = -20.0) -> AudioSegment:
    """Tạo noise trắng 16-bit mono để test nhanh."""
    n = max(1, int(ms * frame_rate / 1000))
    arr = np.random.uniform(-1.0, 1.0, size=n).astype(np.float32)
    pcm16 = (arr * 32767.0).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(frame_rate)
        wf.writeframes(pcm16.tobytes())
    buf.seek(0)
    seg = AudioSegment.from_file(buf, format="wav")
    return seg.apply_gain(level_db)  # type: ignore[attr-defined]
