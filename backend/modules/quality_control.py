"""Quality control — đo LUFS/TruePeak/Duration với type rõ ràng."""
from typing import TypedDict
import io, numpy as np, soundfile as sf
import pyloudnorm as pyln

class MetricsDict(TypedDict):
    lufsIntegrated: float
    truePeakDb: float
    durationSec: float

def _read_wav_bytes(wav_bytes: bytes):
    bio = io.BytesIO(wav_bytes)
    data, sr = sf.read(bio, always_2d=True)  # shape (samples, channels)
    return data, sr

def measure_metrics(wav_bytes: bytes) -> MetricsDict:
    """
    POST: { 'lufsIntegrated': float, 'truePeakDb': float, 'durationSec': float }
    - truePeakDb ở đây xấp xỉ sample peak dBFS (không oversample).
    """
    data, sr = _read_wav_bytes(wav_bytes)
    meter = pyln.Meter(sr)  # ITU-R BS.1770
    lufs = float(meter.integrated_loudness(data))
    peak = float(np.max(np.abs(data)))
    eps = 1e-12
    peak_db = 20.0 * np.log10(max(peak, eps))
    duration = float(data.shape[0]) / float(sr)
    return {"lufsIntegrated": lufs, "truePeakDb": peak_db, "durationSec": duration}
