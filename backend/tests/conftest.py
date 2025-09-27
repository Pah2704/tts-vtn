import io
import wave
from importlib import reload

import numpy as np
import pytest


# --- Giữ 1 outputs dir cho cả session ---
@pytest.fixture(scope="session")
def _outputs_dir_session(tmp_path_factory):
    return tmp_path_factory.mktemp("outputs")


# --- Mỗi test patch env để dùng chung path trên ---
@pytest.fixture(autouse=True)
def _patch_outputs_env(monkeypatch, _outputs_dir_session):
    monkeypatch.setenv("OUTPUTS_DIR", str(_outputs_dir_session))
    try:
        import backend.routes.history as routes_history

        reload(routes_history)
    except Exception:
        pass


try:
    from backend.tests.helpers.audio import gen_sine_wav_bytes as _gen_sine

    def gen_sine_wav_bytes(freq_hz: int = 440, dur_sec: float = 0.5, sr: int = 24_000) -> bytes:
        return _gen_sine(freq_hz=freq_hz, dur_sec=dur_sec, sr=sr)

except Exception:  # pragma: no cover - helper package may be absent in older branches
    pass


@pytest.fixture
def sine_wav():
    sr = 16_000
    dur = 1.0
    t = np.linspace(0, dur, int(sr * dur), endpoint=False, dtype=np.float32)
    waveform = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((waveform * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


@pytest.fixture(autouse=True)
def fake_piper_and_dsp(monkeypatch):
    def _fake_synth(voice_id: str, text: str, speed: float = 1.0):
        sr = 24_000
        base_duration = max(0.05, min(0.6, 0.02 * max(1, len(text) // 10)))
        dur = base_duration / max(0.5, min(2.0, speed))
        t = np.arange(int(sr * dur)) / sr
        pcm = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)[:, None]
        return pcm, sr

    monkeypatch.setattr("backend.engines.piper_engine.synth_text", _fake_synth, raising=True)

    def _fake_dsp(pcm: np.ndarray, sr: int, preset_key: str, overrides=None):
        metrics = {
            "lufs_integrated": -16.0,
            "true_peak_dbfs": -1.0,
            "sr": sr,
            "samples": len(pcm),
        }
        return pcm, metrics

    try:
        monkeypatch.setattr("backend.modules.audio_pipeline.process", _fake_dsp, raising=True)
    except AttributeError:
        monkeypatch.setattr(
            "backend.modules.audio_pipeline.run_pipeline",
            lambda wav_bytes, preset_key=None, utter_wavs=None: _fake_dsp(np.zeros(1, dtype=np.float32), 24_000, preset_key),
            raising=True,
        )


@pytest.fixture(autouse=True)
def celery_inmemory(monkeypatch):
    monkeypatch.setenv("CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "cache+memory://")
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "1")

    import backend.celery_app as celery_app
    reload(celery_app)
