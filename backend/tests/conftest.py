import numpy as np
import os
import pytest
from importlib import reload


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
