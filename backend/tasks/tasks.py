"""Primary Celery tasks for synchronous generation workflow."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from pydub import AudioSegment

from backend.celery_app import celery
from backend.modules.audio_pipeline import run_pipeline
from backend.modules.ducking import apply_ducking
from backend.modules.fx_lib import apply_fades, apply_gain_linear, load_fx, loop_to_length
from backend.modules.tts_manager import SynthesisConfig as EngineCfg, TTSManager
from backend.utils.metrics import clean_metrics


OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
ALLOWED_EMOTIONS = {"happy", "sad", "excited", "calm", "serious", "whisper"}


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


@celery.task(bind=True, name="generate_task")
def generate_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy synchronous generate pipeline executed inside Celery worker."""

    def report(pct: int) -> None:
        self.update_state(state="PROGRESS", meta={"progress": int(pct)})

    job_id = str(getattr(self.request, "id", "job"))

    raw_text = payload.get("text", "")
    text: str = raw_text if isinstance(raw_text, str) else str(raw_text)

    engine_raw = payload.get("engine", "piper")
    engine: str = engine_raw if engine_raw in ("piper", "xtts") else "piper"

    cfg: Dict[str, Any] = payload.get("config") or {}

    voice_id_val = cfg.get("voiceId")
    if not isinstance(voice_id_val, str) or not voice_id_val.strip():
        raise ValueError("voiceId is required (non-empty string)")
    voice_id: str = voice_id_val.strip()

    speed_val = cfg.get("speed", 1.0)
    try:
        speed: float = float(speed_val)
    except (TypeError, ValueError):
        speed = 1.0

    emo_val = cfg.get("emotions")
    emotions_list: List[str] = []
    if isinstance(emo_val, list):
        for e in emo_val:
            if isinstance(e, str) and e in ALLOWED_EMOTIONS:
                emotions_list.append(e)
    emotions_for_engine: Optional[List[str]] = emotions_list or None

    preset_key = cfg.get("presetKey")

    export = payload.get("export") or {}
    fmt_raw = export.get("format", "wav")
    fmt: str = fmt_raw if fmt_raw in ("wav", "mp3", "flac", "m4a") else "wav"
    bitrate_kbps = export.get("bitrateKbps")

    job_dir = OUTPUT_DIR / "async" / job_id
    _ensure_dir(job_dir)

    report(5)
    tts = TTSManager(engine=engine)
    raw_wav: bytes = tts.synthesize(
        text,
        EngineCfg(voice_id=voice_id, speed=speed, emotions=emotions_for_engine),
    )

    original_path = job_dir / "original.wav"
    original_path.write_bytes(raw_wav)

    report(55)
    processed_wav, metrics = run_pipeline(raw_wav, preset_key=preset_key)
    if not isinstance(metrics, dict):
        metrics = dict(metrics or {})
    metrics = clean_metrics(metrics)

    bg_cfg = cfg.get("background") or {}
    kind = (bg_cfg.get("kind") or "none") if isinstance(bg_cfg, dict) else "none"

    voice_seg = AudioSegment.from_file(io.BytesIO(processed_wav), format="wav")

    if kind != "none":
        gain_linear = bg_cfg.get("gain")
        fade_in = bg_cfg.get("fadeInMs") or 0
        fade_out = bg_cfg.get("fadeOutMs") or 0
        enable_duck = bool(bg_cfg.get("ducking", False))

        bg_seg = load_fx(kind)
        try:
            sr_voice = int(getattr(voice_seg, "frame_rate"))
        except Exception:
            sr_voice = 16000
        bg_seg = cast(AudioSegment, cast(Any, bg_seg).set_frame_rate(sr_voice))  # type: ignore[attr-defined]

        target_ms = int(len(cast(Any, voice_seg)))
        bg_seg = loop_to_length(bg_seg, target_ms)
        bg_seg = apply_gain_linear(bg_seg, gain_linear)
        bg_seg = apply_fades(bg_seg, fade_in, fade_out)

        if enable_duck:
            ducked = apply_ducking(bg_seg, voice_seg, reduction_db=9.0, attack_ms=40, release_ms=180)
            mix = cast(AudioSegment, cast(Any, ducked).overlay(voice_seg))  # type: ignore[attr-defined]
        else:
            mix = cast(AudioSegment, cast(Any, bg_seg).overlay(voice_seg))  # type: ignore[attr-defined]
    else:
        mix = voice_seg

    report(85)
    audio = mix
    out_path = job_dir / f"processed.{fmt}"
    if fmt == "wav":
        audio.export(str(out_path), format="wav")
    else:
        br = f"{int(bitrate_kbps)}k" if isinstance(bitrate_kbps, int) else None
        audio.export(str(out_path), format=fmt, bitrate=br)

    report(95)

    return {
        "audio_url": f"/outputs/async/{job_id}/{out_path.name}",
        "raw_url": f"/outputs/async/{job_id}/original.wav",
        "format": fmt,
        "metrics": metrics,
    }


__all__ = ["generate_task"]
