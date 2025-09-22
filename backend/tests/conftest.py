import io, numpy as np, soundfile as sf
import pytest

def gen_sine_wav_bytes(freq=440.0, dur_sec=1.0, sr=24000, amp=0.2):
    t = np.linspace(0, dur_sec, int(sr*dur_sec), endpoint=False)
    x = (amp*np.sin(2*np.pi*freq*t)).astype(np.float32)
    bio = io.BytesIO()
    sf.write(bio, x, sr, format="WAV")
    return bio.getvalue()

@pytest.fixture(scope="session")
def sine_wav():
    return gen_sine_wav_bytes()
