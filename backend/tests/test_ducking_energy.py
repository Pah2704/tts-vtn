from typing import Any, cast
import io, wave, math
import numpy as np
from backend.modules.ducking import apply_ducking
from backend.modules.fx_lib import make_noise_ms
from pydub import AudioSegment

def _rms(seg: AudioSegment, start_ms: int, end_ms: int) -> float:
    sub = cast(Any, seg)[start_ms:end_ms]
    sub = cast(AudioSegment, cast(Any, sub).set_channels(1))  # type: ignore[attr-defined]
    arr = np.array(cast(Any, sub).get_array_of_samples(), dtype=np.float32)  # type: ignore[attr-defined]
    sw = int(getattr(sub, "sample_width", 2))
    if sw == 2:
        arr /= 32768.0
    elif sw == 4:
        arr /= 2147483648.0
    else:
        arr /= float(2 ** (8 * sw - 1))
    return float(np.sqrt(np.mean(arr * arr) + 1e-12))

def test_ducking_reduces_bg_rms_during_voice():
    sr = 16000

    # Nền: white noise -20 dBFS trong 1s (không phải im lặng)
    bg = make_noise_ms(1000, frame_rate=sr, level_db=-20.0)

    # Thoại: tone 440Hz ~300ms ở giữa (300..600ms)
    t = np.arange(0, 0.300, 1.0 / sr, dtype=np.float32)
    tone = (0.5 * np.sin(2 * math.pi * 440 * t)).astype(np.float32)
    pcm16 = (tone * 32767.0).astype(np.int16)

    # Ghi vào WAV trong RAM rồi đọc bằng pydub (để Pylance yên tâm)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(cast(Any, pcm16).tobytes())
    buf.seek(0)
    voice_core = AudioSegment.from_file(buf, format="wav")

    pre = AudioSegment.silent(duration=300, frame_rate=sr)   # type: ignore[attr-defined]
    post = AudioSegment.silent(duration=400, frame_rate=sr)  # type: ignore[attr-defined]
    voice = cast(AudioSegment, cast(Any, pre) + voice_core + post)  # type: ignore[operator]

    out = apply_ducking(bg, voice, reduction_db=9.0)

    rms_before = _rms(bg, 300, 600)
    rms_after = _rms(out, 300, 600)
    assert rms_after < rms_before  # nền bị giảm khi có voice
