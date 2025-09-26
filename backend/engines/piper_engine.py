from __future__ import annotations

import io
import json
import os
import subprocess
import wave
from pathlib import Path
from typing import Tuple

import numpy as np

MODELS_DIR = Path(os.getenv("MODELS_DIR") or "models").resolve()
PIPER_BIN = os.getenv("PIPER_BIN", "/opt/piper/piper")


def _model_paths(voice_id: str) -> Tuple[Path, int]:
    onnx_path = MODELS_DIR / f"{voice_id}.onnx"
    meta_path = MODELS_DIR / f"{voice_id}.onnx.json"
    if not onnx_path.exists():
        raise FileNotFoundError(f"Model not found: {onnx_path}")
    sample_rate = 22050
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text("utf-8"))
            sample_rate = int(meta.get("sample_rate", sample_rate))
        except Exception:
            pass
    return onnx_path, sample_rate


def _wav_bytes_to_np(wav_bytes: bytes) -> Tuple[np.ndarray, int]:
    with io.BytesIO(wav_bytes) as bio:
        with wave.open(bio, "rb") as wf:
            sr = wf.getframerate()
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            frames = wf.readframes(wf.getnframes())
    if sampwidth != 2:
        raise AssertionError("Expect 16-bit PCM from piper")
    pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    pcm = pcm.reshape(-1, channels)
    return pcm, sr


def synth_text(voice_id: str, text: str, speed: float = 1.0) -> Tuple[np.ndarray, int]:
    onnx_path, model_sr = _model_paths(voice_id)
    speed_clamped = max(0.5, min(2.0, speed))
    length_scale = max(0.5, min(2.0, 1.0 / speed_clamped))
    cmd = [
        PIPER_BIN,
        "-m",
        str(onnx_path),
        "--length_scale",
        str(length_scale),
        "-f",
        "-",
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=text.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", "ignore")
        raise RuntimeError(f"Piper failed: {stderr}") from exc
    pcm, sr = _wav_bytes_to_np(proc.stdout)
    return pcm.astype(np.float32), int(sr or model_sr)
