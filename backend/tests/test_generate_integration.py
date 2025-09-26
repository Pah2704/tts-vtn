from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.modules.tts_manager import TTSManager, PiperConfigError


def _probe_piper() -> tuple[bool, str]:
    """Return (is_ready, skip_reason)."""
    try:
        manager = TTSManager(engine="piper")
        manager.validate_runtime()
    except PiperConfigError as exc:
        return False, f"Piper configuration incomplete: {exc}"
    except Exception as exc:  # pragma: no cover - unexpected runtime failure
        return False, f"Piper runtime unavailable: {exc}"
    return True, ""


_PIPER_READY, _PIPER_SKIP_REASON = _probe_piper()


@pytest.mark.skipif(not _PIPER_READY, reason=_PIPER_SKIP_REASON or "Piper runtime not detected")
def test_generate_endpoint_with_real_piper(tmp_path) -> None:
    payload = {
        "mode": "sync",
        "engine": "piper",
        "text": "Xin chao Vietnam",
        "config": {"voiceId": "en_GB-alan-medium", "speed": 1.0},
        "export": {"format": "wav"},
    }

    with TestClient(app) as client:
        response = client.post("/api/generate", json=payload)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["mode"] == "sync"
    assert data["format"] == "wav"
    assert data["metrics"]["durationSec"] > 0.0

    audio_url = data["url"]
    assert audio_url.endswith(".wav")
    filename = data["filename"]

    output_file = Path("backend/outputs") / filename
    assert output_file.exists(), "Generated file missing on disk"
    assert output_file.stat().st_size > 0

    output_file.unlink(missing_ok=True)
