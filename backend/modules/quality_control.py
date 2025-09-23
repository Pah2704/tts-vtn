"""Quality control — đo LUFS/TruePeak/Duration (+ QC mở rộng Phase 2)."""
from typing import TypedDict, NotRequired, List, Tuple
import io, numpy as np, soundfile as sf
import pyloudnorm as pyln

class MetricsDict(TypedDict):
    # Phase 1 (bắt buộc)
    lufsIntegrated: float
    truePeakDb: float
    durationSec: float
    # Phase 2 (optional – tương thích ngược)
    rms: NotRequired[float]
    crestFactor: NotRequired[float]
    snrApprox: NotRequired[float]
    clippingCount: NotRequired[int]
    silenceGapsMs: NotRequired[List[int]]
    qualityScore: NotRequired[int]
    warnings: NotRequired[List[str]]

def _read_wav_bytes(wav_bytes: bytes) -> Tuple[np.ndarray, int]:
    """Đọc WAV bytes -> mono float32 array (n,), sr"""
    bio = io.BytesIO(wav_bytes)
    data, sr = sf.read(bio, dtype="float32", always_2d=True)  # (samples, channels)
    if data.ndim == 2 and data.shape[1] > 1:
        data = data.mean(axis=1, keepdims=True)
    x = data.reshape(-1)  # mono
    return x, sr

def _integrated_lufs(x: np.ndarray, sr: int) -> float:
    meter = pyln.Meter(sr)  # ITU-R BS.1770
    return float(meter.integrated_loudness(x))

def _true_peak_dbfs(x: np.ndarray) -> float:
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    peak = max(peak, 1e-12)  # tránh log(0)
    return 20.0 * np.log10(peak)

def _duration_sec(x: np.ndarray, sr: int) -> float:
    return float(x.size) / float(sr) if sr > 0 else 0.0

def _rms_dbfs(x: np.ndarray) -> float:
    if x.size == 0:
        return -120.0
    rms = np.sqrt(np.mean(np.square(x), dtype=np.float64))
    rms = max(float(rms), 1e-12)
    return 20.0 * np.log10(rms)

def _crest_factor_db(peak_db: float, rms_db: float) -> float:
    return float(peak_db - rms_db)

def _detect_clipping(x: np.ndarray, ceiling_db: float = -1.0) -> int:
    ceiling_amp = 10.0 ** (ceiling_db / 20.0)
    return int(np.count_nonzero(np.abs(x) >= ceiling_amp - 1e-6))

def _estimate_noise_floor_and_silences(
    x: np.ndarray,
    sr: int,
    win_ms: int = 50,
    silence_thresh_dbfs: float = -50.0,
    min_sil_ms: int = 150,
) -> tuple[float, List[int]]:
    """
    Ước lượng noise floor: median RMS của các cửa sổ im lặng.
    Trả về (noise_floor_dbfs, silence_gaps_ms[])
    """
    if x.size == 0 or sr <= 0:
        return -90.0, []
    win = max(1, int(sr * win_ms / 1000))
    n = x.size // win
    if n == 0:
        return -90.0, []
    rms_db = np.empty(n, dtype=np.float32)
    for i in range(n):
        seg = x[i * win : (i + 1) * win]
        # dùng RMS dBFS cho từng cửa sổ
        seg_rms = np.sqrt(np.mean(np.square(seg), dtype=np.float64))
        seg_rms = max(float(seg_rms), 1e-12)
        rms_db[i] = 20.0 * np.log10(seg_rms)
    silence_mask = rms_db <= silence_thresh_dbfs
    if np.any(silence_mask):
        nf = float(np.median(rms_db[silence_mask]))
    else:
        nf = float(np.percentile(rms_db, 20.0))
    # gom các đoạn im lặng liên tục
    gaps: List[int] = []
    if np.any(silence_mask):
        start = None
        for i, is_sil in enumerate(silence_mask):
            if is_sil and start is None:
                start = i
            last = (i == len(silence_mask) - 1)
            if (not is_sil or last) and start is not None:
                end = i if not is_sil else i + 1
                dur_ms = int((end - start) * win_ms)
                if dur_ms >= min_sil_ms:
                    gaps.append(dur_ms)
                start = None
    return nf, gaps

def measure_metrics(wav_bytes: bytes) -> MetricsDict:
    """
       Phase 2 (nâng cấp in-place):
    - giữ: lufsIntegrated, truePeakDb, durationSec
    - thêm: rms, crestFactor, snrApprox, clippingCount, silenceGapsMs, qualityScore, warnings
    (các trường mới là optional khi được map sang model Pydantic bên ngoài)
    """
    x, sr = _read_wav_bytes(wav_bytes)

    # Phase 1 metrics
    lufs = _integrated_lufs(x, sr)
    peak_db = _true_peak_dbfs(x)
    duration = _duration_sec(x, sr)

    # Phase 2 metrics
    rms_db = _rms_dbfs(x)
    crest = _crest_factor_db(peak_db, rms_db)
    noise_floor_db, silence_gaps = _estimate_noise_floor_and_silences(x, sr)
    snr_approx = float(rms_db - noise_floor_db)
    clipping_count = _detect_clipping(x, ceiling_db=-1.0)

    # Quality score (0–100), rule-based nhẹ
    score = 100
    warnings: List[str] = []
    if abs(lufs - (-16.0)) > 0.8:
        score -= 8
        warnings.append("LUFS out-of-range")
    if peak_db > -1.0 + 1e-3:
        score -= 15
        warnings.append("True Peak above -1 dBFS")
    if snr_approx < 18.0:
        score -= 10
        warnings.append("Low SNR")
    if crest < 3.0:
        score -= 6
        warnings.append("Low crest factor")
    if clipping_count > 0:
        score -= 15
        warnings.append("Detected clipping")
    score = max(0, min(100, score))

    return {
        "lufsIntegrated": float(lufs),
        "truePeakDb": float(peak_db),
        "durationSec": float(duration),
        # mở rộng (optional)
        "rms": float(rms_db),
        "crestFactor": float(crest),
        "snrApprox": float(snr_approx),
        "clippingCount": int(clipping_count),
        "silenceGapsMs": [int(ms) for ms in silence_gaps],
        "qualityScore": int(score),
        "warnings": warnings,
    }
