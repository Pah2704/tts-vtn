from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

MODELS_DIR = Path(os.getenv("MODELS_DIR") or "models").resolve()


def _models_dir() -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return MODELS_DIR


class VoiceInfo(BaseModel):
    voiceId: str
    lang: Optional[str] = None
    name: Optional[str] = None
    size: Optional[str] = None
    meta: dict | None = None


VOICE_RE = re.compile(r"^([a-z]{2}_[A-Z]{2})-([a-z0-9]+)-([a-z0-9]+)$")


def _scan_voices() -> List[VoiceInfo]:
    models_path = _models_dir()
    voices: List[VoiceInfo] = []
    for onnx in sorted(models_path.glob("**/*.onnx")):
        voice_id = onnx.stem
        lang = name = size = None
        match = VOICE_RE.match(voice_id)
        if match:
            lang, name, size = match.group(1), match.group(2), match.group(3)
        meta = None
        meta_path = onnx.with_suffix(".onnx.json")
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text("utf-8"))
            except Exception:
                meta = None
        voices.append(
            VoiceInfo(
                voiceId=voice_id,
                lang=lang,
                name=name,
                size=size,
                meta=meta,
            )
        )
    return voices


@router.get("/voices", response_model=list[VoiceInfo])
def list_voices() -> List[VoiceInfo]:
    return _scan_voices()
