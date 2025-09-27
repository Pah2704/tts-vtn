import io
import wave
import numpy as np


def gen_sine_wav_bytes(
    freq_hz: int = 440,
    dur_sec: float = 0.5,
    sr: int = 24_000,
    amp: float = 0.3,
    channels: int = 1,
) -> bytes:
    """Generate a small sine-wave WAV (int16) and return as bytes."""
    assert channels in (1, 2), "channels must be 1 or 2"
    n = max(1, int(sr * dur_sec))
    t = np.arange(n, dtype=np.float32) / float(sr)
    pcm = (amp * np.sin(2 * np.pi * freq_hz * t) * 32767.0).astype(np.int16)

    if channels == 2:
        pcm = np.column_stack([pcm, pcm]).ravel().astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()
