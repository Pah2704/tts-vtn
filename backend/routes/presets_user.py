from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError

router = APIRouter()

DEFAULT_PRESETS_DIR = Path(__file__).resolve().parents[1] / "presets_user"


def _resolve_dir() -> Path:
    path = Path(os.getenv("PRESETS_USER_DIR", str(DEFAULT_PRESETS_DIR)))
    path.mkdir(parents=True, exist_ok=True)
    return path

SAFE_KEY = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


class PresetDefaults(BaseModel):
    voiceId: Optional[str] = None
    speed: Optional[float] = Field(default=None, ge=0.5, le=2.0)


class PresetDSP(BaseModel):
    nr: Optional[str] = None
    eq: Optional[str] = None
    lufsTarget: Optional[float] = None
    truePeakCeiling: Optional[float] = None


class PresetSegmentation(BaseModel):
    strategy: Optional[str] = None
    autoBreakMs: Optional[int] = None


class PresetBackground(BaseModel):
    kind: Optional[str] = None
    gain: Optional[float] = None


class UserPreset(BaseModel):
    key: str = Field(..., pattern=SAFE_KEY.pattern)
    title: str
    engine: str
    defaults: PresetDefaults = PresetDefaults()
    dsp: Optional[PresetDSP] = None
    segmentation: Optional[PresetSegmentation] = None
    background: Optional[PresetBackground] = None


def _path_for(key: str) -> Path:
    return _resolve_dir() / f"{key}.json"


@router.get("/presets_user", response_model=list[UserPreset])
def list_presets() -> list[UserPreset]:
    presets: list[UserPreset] = []
    directory = _resolve_dir()
    for path in directory.glob("*.json"):
        try:
            presets.append(UserPreset(**json.loads(path.read_text("utf-8"))))
        except Exception:
            continue
    return presets


@router.put("/presets_user/{key}", response_model=UserPreset)
def put_preset(key: str, payload: UserPreset) -> UserPreset:
    if not SAFE_KEY.match(key):
        raise HTTPException(status_code=400, detail={"code": "bad_key", "message": "Invalid preset key"})
    if payload.key != key:
        raise HTTPException(status_code=400, detail={"code": "key_mismatch", "message": "Key in path and body must match"})
    try:
        data = payload.model_dump()
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_preset", "message": exc.errors()}) from exc
    _path_for(key).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


@router.delete("/presets_user/{key}")
def delete_preset(key: str) -> dict[str, Any]:
    if not SAFE_KEY.match(key):
        raise HTTPException(status_code=400, detail={"code": "bad_key", "message": "Invalid preset key"})
    path = _path_for(key)
    if not path.exists():
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Preset not found"})
    path.unlink()
    return {"ok": True}
