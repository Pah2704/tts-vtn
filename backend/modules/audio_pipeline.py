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


# Optional deps (bypass if missing)
try:  # NR
    import noisereduce as nr  # type: ignore
except Exception:  # pragma: no cover
    nr = None  # type: ignore

try:  # EQ/filters
    from scipy.signal import butter, sosfilt, iirpeak  # type: ignore
except Exception:  # pragma: no cover
    butter = sosfilt = iirpeak = None  # type: ignore


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
    """Spectral gating đơn giản (noisereduce). Nếu thiếu lib → bypass."""
    if x.size == 0 or nr is None:
        return x
    # Map mức độ → prop_decrease + time constant
    if strength == "strong":
        prop, tc = 1.0, 0.6
    elif strength == "medium":
        prop, tc = 0.85, 0.5
    else:
        prop, tc = 0.7, 0.4
    try:
        y = nr.reduce_noise(
            y=x.astype(np.float32, copy=False),
            sr=sr,
            stationary=True,
            prop_decrease=prop,
            time_constant_s=tc,
            freq_mask_smooth_hz=500,
            n_std_thresh_stationary=1.5,
        )
        return np.clip(y, -1.0, 1.0)
    except Exception:
        return x


def eq_apply(
    x: np.ndarray,
    sr: int,
    profile: Literal["flat", "voice_clarity", "warmth", "brightness"],
) -> np.ndarray:
    """
    EQ tối thiểu bằng IIR:
    - voice_clarity: high-pass 80 Hz + peaking +3 dB @ 3 kHz (Q≈1.0)
    - warmth: high-pass 60 Hz + peaking +2 dB @ 200 Hz, -2 dB @ 4 kHz
    - brightness: high-pass 80 Hz + peaking +3 dB @ 8 kHz
    Nếu thiếu SciPy → bypass.
    """
    if x.size == 0 or butter is None or sosfilt is None:
        return x

    # Narrow type cho Pylance (butter/sosfilt không còn Optional)
    assert butter is not None and sosfilt is not None

    y = x.astype(np.float32, copy=True)

    def hp(y_in: np.ndarray, fc: float) -> np.ndarray:
        # 2nd-order Butter HPF
        sos = butter(2, fc, btype="highpass", fs=sr, output="sos")  # type: ignore[call-arg]
        return np.asarray(sosfilt(sos, y_in), dtype=np.float32)      # type: ignore[arg-type]

    def peak(y_in: np.ndarray, f0: float, gain_db: float, q: float) -> np.ndarray:
        # Simple peaking: band-pass then mix (poor-man's peq). Nếu thiếu iirpeak → bypass.
        if iirpeak is None or gain_db == 0.0:
            return y_in
        from scipy.signal import lfilter  # type: ignore
        b, a = iirpeak(f0, Q=q, fs=sr)                      # type: ignore[call-arg]
        b = np.asarray(b, dtype=np.float32)
        a = np.asarray(a, dtype=np.float32)
        band = np.asarray(lfilter(b, a, y_in), dtype=np.float32)  # type: ignore[arg-type]
        g = float(10.0 ** (gain_db / 20.0))
        return np.clip(y_in + (g - 1.0) * band, -1.0, 1.0)

    try:
        if profile == "flat":
            return y
        if profile == "voice_clarity":
            y = hp(y, 80.0)
            y = peak(y, 3000.0, +3.0, q=1.0)
            return y
        if profile == "warmth":
            y = hp(y, 60.0)
            y = peak(y, 200.0, +2.0, q=0.8)
            y = peak(y, 4000.0, -2.0, q=1.2)
            return y
        if profile == "brightness":
            y = hp(y, 80.0)
            y = peak(y, 8000.0, +3.0, q=0.9)
            return y
        return y
    except Exception:
        # an toàn nếu SciPy có vấn đề runtime
        return x

    """
    EQ tối thiểu bằng IIR:
    - voice_clarity: high-pass 80 Hz + peaking +3 dB @ 3 kHz (Q≈1.0)
    - warmth: high-pass 60 Hz nhẹ + peaking +2 dB @ 200 Hz, -2 dB @ 4 kHz
    - brightness: high-pass 80 Hz + peaking +3 dB @ 8 kHz
    Nếu thiếu SciPy → bypass.
    """
    if x.size == 0 or butter is None or sosfilt is None:
        return x

    y = x.astype(np.float32, copy=True)

    def hp(y: np.ndarray, fc: float) -> np.ndarray:
        # 2nd-order Butter HPF
        sos = butter(2, fc, btype="highpass", fs=sr, output="sos")
        return sosfilt(sos, y)

    def peak(y: np.ndarray, f0: float, gain_db: float, q: float) -> np.ndarray:
        if iirpeak is None or gain_db == 0.0:
            return y
        # iirpeak returns (b, a). Convert to SOS via butter as a wrapper is overkill;
        # apply biquad manually by filtering twice is unnecessary—use lfilter via sos? Keep simple:
        # Approx: apply a narrow bandpass and mix (poor-man peq). Enough for minimal EQ.
        from scipy.signal import lfilter  # type: ignore
        bw = f0 / q
        b, a = iirpeak(f0, Q=q, fs=sr)
        band = lfilter(b, a, y)
        g = 10 ** (gain_db / 20.0)
        return np.clip(y + (g - 1.0) * band, -1.0, 1.0)

    try:
        if profile == "flat":
            return y
        if profile == "voice_clarity":
            y = hp(y, 80.0)
            y = peak(y, 3000.0, +3.0, q=1.0)
            return y
        if profile == "warmth":
            y = hp(y, 60.0)
            y = peak(y, 200.0, +2.0, q=0.8)
            y = peak(y, 4000.0, -2.0, q=1.2)
            return y
        if profile == "brightness":
            y = hp(y, 80.0)
            y = peak(y, 8000.0, +3.0, q=0.9)
            return y
        return y
    except Exception:
        return x


def compress(x: np.ndarray, sr: int, comp: CompParams) -> np.ndarray:
    """
    Compressor feed-forward tối giản (soft-knee gần đúng).
    - threshold (dBFS), ratio, attack/release (ms), makeup (dB).
    - ratio≈1 → bypass.
    """
    ratio = float(comp.get("ratio", 1.0) or 1.0)
    if x.size == 0 or ratio <= 1.02:
        return x

    thr = float(comp.get("threshold", -24.0))
    att = max(1.0, float(comp.get("attack", 15.0)))   # ms
    rel = max(10.0, float(comp.get("release", 150.0))) # ms
    mk  = float(comp.get("makeup", 0.0))

    # Envelope RMS (window ~ 10ms) → level dBFS
    win = max(1, int(sr * 0.010))
    # pad for simple moving RMS
    pad = np.pad(x, (win // 2, win - win // 2), mode="edge")
    # moving RMS
    sq = pad * pad
    cumsum = np.cumsum(sq, dtype=np.float64)
    rms = np.sqrt((cumsum[win:] - cumsum[:-win]) / win, dtype=np.float64)
    # align length
    rms = rms[: x.size]
    rms = np.maximum(rms, 1e-12)
    lvl_db = 20.0 * np.log10(rms)

    # Gain computer w/ soft knee (6 dB)
    knee = 6.0
    over = lvl_db - thr
    # region masks
    below = over <= -knee / 2
    knee_zone = (over > -knee / 2) & (over < knee / 2)
    above = over >= knee / 2
    gain_red_db = np.zeros_like(lvl_db)
    # knee formula (approx)
    gain_red_db[knee_zone] = (1.0 - 1.0 / ratio) * ((over[knee_zone] + knee / 2) ** 2) / (2 * knee)
    gain_red_db[above] = (1.0 - 1.0 / ratio) * (over[above])

    # Attack/Release smoothing on gain reduction
    att_a = np.exp(-1.0 / max(1, int(sr * att / 1000.0)))
    rel_a = np.exp(-1.0 / max(1, int(sr * rel / 1000.0)))
    gr_s = np.zeros_like(gain_red_db)
    g = 0.0
    for i, gr in enumerate(gain_red_db):
        target = gr
        if gr > g:  # more reduction → attack
            g = att_a * g + (1 - att_a) * target
        else:       # less reduction → release
            g = rel_a * g + (1 - rel_a) * target
        gr_s[i] = g

    # Convert gain reduction dB → linear, apply + makeup
    gain_db = -gr_s + mk
    gain = 10.0 ** (gain_db / 20.0)
    y = x * gain.astype(np.float32, copy=False)
    return np.clip(y, -1.0, 1.0)


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
