from importlib import reload


def test_xtts_task_smoke(monkeypatch, tmp_path):
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))
    from backend.services import render_service

    reload(render_service)

    from backend.tasks.xtts_task import xtts_generate_task

    payload = {
        "text": "Hello world.",
        "textMode": "plain",
        "engine": "xtts",
        "voiceId": "en_GB-alan-medium",
        "speed": 1.0,
        "preset": "podcast_standard",
        "exportFormat": "wav",
        "config": {"segmentation": {"strategy": "punctuation", "autoBreakMs": 160}},
    }
    result = xtts_generate_task.apply(args=[payload]).get()
    assert result["ok"] is True
    assert result["url"].endswith(".wav")
