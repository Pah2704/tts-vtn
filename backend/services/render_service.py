from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import time
import uuid
import wave
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

from backend.modules import audio_pipeline
from backend.modules.assembler import assemble_linear_pcm
from backend.modules.ssml_parser import Utterance
from backend.engines import piper_engine

OUTPUTS_DIR = Path(os.getenv("OUTPUTS_DIR") or "backend/outputs").resolve()
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(prefix: str, ext: str = "wav") -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    uid = uuid.uuid4().hex[:6]
    return OUTPUTS_DIR / f"{prefix}-{timestamp}-{uid}.{ext}"


def _pcm_to_wav_bytes(pcm: np.ndarray, sr: int) -> bytes:
    data = (np.clip(pcm, -1.0, 1.0) * 32767.0).astype(np.int16)
    channels = data.shape[1] if pcm.ndim == 2 else 1
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(data.tobytes())
    return bio.getvalue()


def _write_wav(path: Path, pcm: np.ndarray, sr: int) -> None:
    path.write_bytes(_pcm_to_wav_bytes(pcm, sr))


def _save_audio(out_path: Path, pcm: np.ndarray, sr: int, ext: str) -> None:
    ext = ext.lower().lstrip(".")
    if ext == "wav":
        _write_wav(out_path, pcm, sr)
        return

    try:
        import soundfile as sf  # type: ignore

        if ext == "flac":
            sf.write(out_path, pcm.squeeze(), sr, format="FLAC", subtype="PCM_16")
            return
        if ext == "ogg":
            sf.write(out_path, pcm.squeeze(), sr, format="OGG", subtype="VORBIS")
            return
    except Exception:  # pragma: no cover - optional dependency
        pass

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        _write_wav(tmp_path, pcm, sr)
        codec_args: list[str] = []
        if ext == "mp3":
            codec_args = ["-c:a", "libmp3lame", "-b:a", os.getenv("EXPORT_BITRATE", "192k")]
        elif ext in ("m4a", "aac"):
            codec_args = ["-c:a", "aac", "-b:a", os.getenv("EXPORT_BITRATE", "192k")]
        elif ext == "flac":
            codec_args = ["-c:a", "flac"]
        elif ext == "ogg":
            codec_args = ["-c:a", "libvorbis", "-q:a", os.getenv("EXPORT_OGG_Q", "5")]
        else:
            ext = "mp3"
            out_path = out_path.with_suffix(".mp3")
            codec_args = ["-c:a", "libmp3lame", "-b:a", os.getenv("EXPORT_BITRATE", "192k")]

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(tmp_path),
            *codec_args,
            str(out_path),
        ]
        subprocess.run(cmd, check=True)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:  # pragma: no cover
            pass


def render_timeline_piper(
    timeline: List[Utterance],
    preset_key: str = "podcast_standard",
    dsp_overrides: Dict | None = None,
    export_ext: str = "wav",
) -> Tuple[Path, Dict]:
    chunks: List[np.ndarray] = []
    breaks: List[int] = []
    sr_ref: int | None = None

    for utterance in timeline:
        pcm, sr = piper_engine.synth_text(utterance.voiceId, utterance.text, speed=utterance.speed)
        if sr_ref is None:
            sr_ref = sr
        elif sr != sr_ref:
            ratio = sr_ref / sr
            idx = (np.arange(int(len(pcm) * ratio)) / ratio).astype(np.int64)
            idx = np.clip(idx, 0, len(pcm) - 1)
            pcm = pcm[idx]
        chunks.append(pcm)
        breaks.append(int(utterance.breaksAfterMs or 0))

    sr = int(sr_ref or 24_000)
    assembled = assemble_linear_pcm(chunks, sr, breaks_after_ms=breaks, crossfade_ms=10)

    processed_pcm, metrics = audio_pipeline.process(
        assembled,
        sr,
        preset_key=preset_key,
        overrides=dsp_overrides or {},
    )

    out_path = _safe_filename(f"piper-{preset_key}", export_ext or "wav")
    _save_audio(out_path, processed_pcm, sr, export_ext or "wav")

    duration = len(processed_pcm) / sr
    sidecar = {
        "engine": "piper",
        "preset": preset_key,
        "voices": sorted({u.voiceId for u in timeline}),
        "timeline": [asdict(u) for u in timeline][:20],
        "duration": float(round(duration, 3)),
        "samplerate": sr,
        "metrics": metrics,
        "createdAt": int(time.time()),
        "export": out_path.suffix.lstrip("."),
    }
    meta_path = out_path.with_suffix(out_path.suffix + ".meta.json")
    meta_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path, sidecar
