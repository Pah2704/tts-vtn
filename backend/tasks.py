# backend/tasks.py
from __future__ import annotations
from typing import Dict, Any, Optional, List, cast
from pathlib import Path
import io

from .celery_app import celery_app
from backend.modules.tts_manager import TTSManager, SynthesisConfig as EngineCfg
from backend.modules.audio_pipeline import run_pipeline
from pydub import AudioSegment
from backend.modules.fx_lib import load_fx, loop_to_length, apply_gain_linear, apply_fades
from backend.modules.ducking import apply_ducking

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
ALLOWED_EMOTIONS = {"happy", "sad", "excited", "calm", "serious", "whisper"}


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


@celery_app.task(bind=True, name="generate_task")
def generate_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase 3 - bước đầu: tạo artifacts cho async job.
    - Lưu original.wav (sau TTS)
    - Chạy pipeline Phase 2 -> processed.wav
    - (Optional) Trộn background FX + auto-ducking
    - Export theo format yêu cầu (mặc định wav)
    - Cập nhật progress (meta.progress)
    """
    def report(pct: int) -> None:
        self.update_state(state="PROGRESS", meta={"progress": int(pct)})

    job_id = str(getattr(self.request, "id", "job"))

    # ==== Lấy & chuẩn hóa tham số ====
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
    emotions_for_engine: Any = emotions_list if emotions_list else None

    preset_key = cfg.get("presetKey")

    export = payload.get("export") or {}
    fmt_raw = export.get("format", "wav")
    fmt: str = fmt_raw if fmt_raw in ("wav", "mp3", "flac", "m4a") else "wav"
    bitrate_kbps = export.get("bitrateKbps")

    # ==== Thư mục output ====
    job_dir = OUTPUT_DIR / "async" / job_id
    _ensure_dir(job_dir)

    # ==== 1) TTS ====
    report(5)
    tts = TTSManager(engine=engine)
    raw_wav: bytes = tts.synthesize(
        text, EngineCfg(voice_id=voice_id, speed=speed, emotions=emotions_for_engine)
    )

    # Lưu original.wav cho A/B
    original_path = job_dir / "original.wav"
    original_path.write_bytes(raw_wav)

    # ==== 2) Pipeline (DSP/QC Phase 2) ====
    report(55)
    processed_wav, metrics = run_pipeline(raw_wav, preset_key=preset_key)
    if not isinstance(metrics, dict):
        metrics = dict(metrics or {})

    # ==== 2.5) Background FX + ducking (optional) ====
    bg_cfg = cfg.get("background") or {}
    kind = (bg_cfg.get("kind") or "none") if isinstance(bg_cfg, dict) else "none"

    voice_seg = AudioSegment.from_file(io.BytesIO(processed_wav), format="wav")

    if kind != "none":
        gain_linear = bg_cfg.get("gain")          # 0.0 .. 0.5 hoặc None
        fade_in = bg_cfg.get("fadeInMs") or 0
        fade_out = bg_cfg.get("fadeOutMs") or 0
        enable_duck = bool(bg_cfg.get("ducking", False))

        bg_seg = load_fx(kind)
        # Đồng bộ SR với voice (fallback 16000 nếu stub không expose)
        try:
            sr_voice = int(getattr(voice_seg, "frame_rate"))
        except Exception:
            sr_voice = 16000
        bg_seg = cast(AudioSegment, cast(Any, bg_seg).set_frame_rate(sr_voice))  # type: ignore[attr-defined]

        target_ms = int(len(cast(Any, voice_seg)))  # pydub: len(seg) => ms
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

    # ==== 3) Export processed.{fmt} ====
    report(85)
    audio = mix
    out_path = job_dir / f"processed.{fmt}"
    if fmt == "wav":
        audio.export(str(out_path), format="wav")
    else:
        br = f"{int(bitrate_kbps)}k" if isinstance(bitrate_kbps, int) else None
        audio.export(str(out_path), format=fmt, bitrate=br)

    # Hoàn tất
    report(95)

    # ==== 4) Kết quả cho router /result ====
    return {
        "audio_url": f"/outputs/async/{job_id}/{out_path.name}",
        "raw_url": f"/outputs/async/{job_id}/original.wav",
        "format": fmt,
        "metrics": metrics,
    }
