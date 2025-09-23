"""
Audio pipeline — Phase 2 scaffold
- Mô-đun: Noise Reduction -> EQ -> Compression -> Normalize (LUFS) -> True Peak Limit
- Hỗ trợ preset (presetKey) và hook voice-level matching cho hội thoại
- Giữ hành vi cũ khi chưa có preset: normalize -16 LUFS + peak limit -1 dBFS
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Tuple, cast

import io
import numpy as np
import soundfile as sf
import pyloudnorm as pyln

from .quality_control import measure_metrics, MetricsDict
from .presets import PRESETS, PresetKey, CompParams


# =========================
# I/O helpers
# =========================
def _read_wav_bytes(wav_bytes: bytes) -> Tuple[np.ndarray, int]:
    """Đọc bytes WAV -> (mono float32 array [-1..1], sample_rate)."""
    bio = io.BytesIO(wav_bytes)
    data, sr = sf.read(bio, dtype="float32", always_2d=True)
    # mono-ize
    if data.ndim == 2 and data.shape[1] > 1:
        data = data.mean(axis=1, keepdims=True)
    # shape -> (n_samples,)
    data = data.reshape(-1)
    return data, sr


def _write_wav_bytes(data: np.ndarray, sr: int) -> bytes:
    """Ghi (float32, mono) -> WAV bytes (PCM_16)."""
    bio = io.BytesIO()
    sf.write(bio, data, sr, subtype="PCM_16", format="WAV")
    return bio.getvalue()


# =========================
# DSP primitives
# =========================
def normalize_to_lufs_array(x: np.ndarray, sr: int, target_lufs: float = -16.0) -> np.ndarray:
    """Chuẩn hóa integrated loudness về target LUFS (đơn giản, dùng pyloudnorm)."""
    if x.size == 0:
        return x
    meter = pyln.Meter(sr)
    # pyloudnorm kỳ vọng shape (n,) hoặc (n,channels); ta đang mono (n,)
    loudness = float(meter.integrated_loudness(x))
    gain_db = float(target_lufs - loudness)
    gain = 10.0 ** (gain_db / 20.0)
    y = x * gain
    return np.clip(y, -1.0, 1.0)


def true_peak_limit_array(x: np.ndarray, ceiling_db: float = -1.0) -> np.ndarray:
    """Limiter đơn giản (clip ceiling, không oversampling)."""
    if x.size == 0:
        return x
    ceiling_amp = 10.0 ** (ceiling_db / 20.0)
    return np.clip(x, -ceiling_amp, ceiling_amp)


# =========================
# Preset mapping
# =========================
@dataclass
class DspParams:
    nr_strength: Literal["light", "medium", "strong"]
    eq_profile: Literal["flat", "voice_clarity", "warmth", "brightness"]
    comp: CompParams  # threshold, ratio, attack, release, makeup
    lufs_target: float
    peak_ceiling: float
    level_match_enabled: bool
    per_utt_target: Optional[float]


def _preset_to_params(key: Optional[PresetKey]) -> DspParams:
    """Chuyển presetKey (hoặc None) -> tham số DSP nội bộ."""
    if not key or key not in PRESETS:
        # Fallback Phase 1
        default_comp: CompParams = {"threshold": -24.0, "ratio": 1.0, "attack": 20.0, "release": 200.0, "makeup": 0.0}
        return DspParams(
            nr_strength="light",
            eq_profile="flat",
            comp=default_comp,
            lufs_target=-16.0,
            peak_ceiling=-1.0,
            level_match_enabled=False,
            per_utt_target=None,
        )
    d = PRESETS[key]["dsp"]
    default_comp: CompParams = {"threshold": -24.0, "ratio": 1.0, "attack": 20.0, "release": 200.0, "makeup": 0.0}
    comp = cast(CompParams, d.get("comp", default_comp))
    return DspParams(
        nr_strength=d.get("nr_strength", "light"),
        eq_profile=d.get("eq_profile", "flat"),
        comp=comp,
        lufs_target=float(d["lufs_target"]),
        peak_ceiling=float(d["peak_ceiling"]),
        level_match_enabled=d.get("level_match", {}).get("enabled", False),
        per_utt_target=d.get("level_match", {}).get("per_utterance_target"),
    )


# =========================
# Placeholders (bypass an toàn)
# =========================
def noise_reduce(x: np.ndarray, sr: int, strength: Literal["light", "medium", "strong"]) -> np.ndarray:
    """TODO: spectral gating (noisereduce/scipy). Hiện tại bypass."""
    return x


def eq_apply(x: np.ndarray, sr: int, profile: Literal["flat", "voice_clarity", "warmth", "brightness"]) -> np.ndarray:
    """TODO: 3–5 band (biquad). 'flat' => bypass."""
    return x


def compress(x: np.ndarray, sr: int, comp: CompParams) -> np.ndarray:
    """TODO: soft-knee compressor. ratio ~ 1.0 => bypass."""
    ratio = float(comp.get("ratio", 1.0) or 1.0)
    if ratio <= 1.05:
        return x
    # Placeholder: chưa nén thật, giữ nguyên
    return x


def assemble_with_crossfade(chunks: List[np.ndarray], sr: int, ms: int = 8) -> np.ndarray:
    """Ghép nhiều câu với crossfade ngắn để tránh click (placeholder)."""
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    out = chunks[0].astype(np.float32, copy=True)
    nxf = max(1, int(sr * ms / 1000))
    for i in range(1, len(chunks)):
        a = out
        b = chunks[i].astype(np.float32, copy=False)
        pre = a[:-nxf] if a.size > nxf else np.zeros(0, dtype=a.dtype)
        xa = a[-nxf:] if a.size >= nxf else a
        xb = b[:nxf] if b.size >= nxf else b
        n = min(xa.size, xb.size)
        if n == 0:
            out = np.concatenate([a, b], axis=0)
            continue
        t = np.linspace(0.0, 1.0, n, dtype=np.float32)
        xf = (1.0 - t) * xa[:n] + t * xb[:n]
        out = np.concatenate([pre, xf, b[n:]], axis=0)
    return np.clip(out, -1.0, 1.0)


# =========================
# Public API
# =========================
def run_pipeline(
    wav_bytes: bytes,
    *,
    preset_key: Optional[PresetKey] = None,
    utter_wavs: Optional[List[bytes]] = None,  # dùng cho hội thoại (nếu có)
) -> Tuple[bytes, MetricsDict]:
    """
    Phase 2: Pipeline xử lý theo preset.
    - Nếu không có preset -> fallback Phase 1 (-16 LUFS, -1 dBTP).
    - NR/EQ/Comp hiện là placeholder (bypass), sẽ hiện thực thật ở bước sau.
    """
    x, sr = _read_wav_bytes(wav_bytes)
    p = _preset_to_params(preset_key)

    # 1) NR
    x = noise_reduce(x, sr, p.nr_strength)
    # 2) EQ
    x = eq_apply(x, sr, p.eq_profile)
    # 3) Comp
    x = compress(x, sr, p.comp)

    # 4) Normalize -> 5) Limit
    x = normalize_to_lufs_array(x, sr, target_lufs=p.lufs_target)
    x = true_peak_limit_array(x, ceiling_db=p.peak_ceiling)

    # 6) (Optional) Voice-level matching + assemble
    if utter_wavs and p.level_match_enabled:
        parts = []
        for uw in utter_wavs:
            u, _ = _read_wav_bytes(uw)
            u = normalize_to_lufs_array(u, sr, target_lufs=p.per_utt_target or p.lufs_target)
            parts.append(u)
        x = assemble_with_crossfade(parts, sr, ms=8)
        x = normalize_to_lufs_array(x, sr, target_lufs=p.lufs_target)
        x = true_peak_limit_array(x, ceiling_db=p.peak_ceiling)

    out_bytes = _write_wav_bytes(x.astype(np.float32, copy=False), sr)
    metrics: MetricsDict = measure_metrics(out_bytes)  # hiện trả LUFS/TruePeak/Duration
    return out_bytes, metrics

# ===== Backward-compat wrappers (Phase 1 tests expect these) =====
def normalize_to_lufs(wav_bytes: bytes, target_lufs: float = -16.0) -> bytes:
    """Compat: nhận WAV bytes, trả WAV bytes đã normalize về target LUFS."""
    x, sr = _read_wav_bytes(wav_bytes)
    y = normalize_to_lufs_array(x, sr, target_lufs=target_lufs)
    return _write_wav_bytes(y, sr)

def peak_limit(wav_bytes: bytes, ceiling_db: float = -1.0) -> bytes:
    """Compat: nhận WAV bytes, trả WAV bytes đã limit về trần peak (dBFS)."""
    x, sr = _read_wav_bytes(wav_bytes)
    y = true_peak_limit_array(x, ceiling_db=ceiling_db)
    return _write_wav_bytes(y, sr)
