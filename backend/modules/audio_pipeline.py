"""Audio pipeline — normalize về target LUFS và peak limit đơn giản."""
from typing import Tuple
import io, numpy as np, soundfile as sf
import pyloudnorm as pyln
from .quality_control import measure_metrics, MetricsDict

def _read_wav_bytes(wav_bytes: bytes):
    bio = io.BytesIO(wav_bytes)
    data, sr = sf.read(bio, always_2d=True)
    return data, sr

def _write_wav_bytes(data, sr) -> bytes:
    bio = io.BytesIO()
    sf.write(bio, data, sr, format="WAV")
    return bio.getvalue()

def normalize_to_lufs(wav_bytes: bytes, target_lufs: float = -16.0) -> bytes:
    data, sr = _read_wav_bytes(wav_bytes)
    meter = pyln.Meter(sr)
    loudness = meter.integrated_loudness(data)
    gain_db = float(target_lufs - loudness)
    gain = 10.0 ** (gain_db / 20.0)
    data2 = np.clip(data * gain, -1.0, 1.0)
    return _write_wav_bytes(data2, sr)

def peak_limit(wav_bytes: bytes, ceiling_db: float = -1.0) -> bytes:
    data, sr = _read_wav_bytes(wav_bytes)
    ceiling_amp = 10.0 ** (ceiling_db / 20.0)
    data2 = np.clip(data, -ceiling_amp, ceiling_amp)
    return _write_wav_bytes(data2, sr)

def run_pipeline(wav_bytes: bytes) -> Tuple[bytes, MetricsDict]:
    x = normalize_to_lufs(wav_bytes, -16.0)
    y = peak_limit(x, -1.0)
    metrics: MetricsDict = measure_metrics(y)
    return y, metrics
