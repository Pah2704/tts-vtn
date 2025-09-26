from __future__ import annotations

from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

TextMode = Literal["plain", "ssml"]


class SegmentationConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    strategy: Literal["punctuation", "newline"] = "punctuation"
    maxChunkChars: Optional[int] = Field(default=None, ge=10, le=5000)
    mergeShortBelow: Optional[int] = Field(default=None, ge=0, le=200)
    autoBreakMs: Optional[int] = Field(default=None, ge=0, le=5000)


class SSMLConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    validate_: bool = Field(True, alias="validate")
    stripUnknown: bool = True
    errorMode: Literal["fail", "warn"] = "warn"


class DuckingConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    depthDb: float = 6.0
    attackMs: int = 60
    releaseMs: int = 250


class DSPOverride(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nr: Optional[Literal["off", "light", "medium", "strong"]] = None
    eq: Optional[Literal["flat", "voice_clarity", "warmth", "brightness"]] = None
    lufsTarget: Optional[float] = None
    truePeakCeiling: Optional[float] = None


class BackgroundConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["none", "file", "rain", "cafe", "forest", "ocean", "fire", "wind"] = "none"
    path: Optional[str] = None
    gain: float = 0.0
    ducking: Optional[DuckingConfig] = None


class GenerateConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    segmentation: Optional[SegmentationConfig] = None
    ssml: Optional[SSMLConfig] = None
    dsp: Optional[DSPOverride] = None
    background: Optional[BackgroundConfig] = None


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str
    textMode: TextMode = "plain"
    engine: Literal["piper", "xtts"]
    voiceId: str
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    preset: Optional[str] = "podcast_standard"
    exportFormat: Optional[Literal["wav", "mp3", "flac", "m4a"]] = "wav"
    config: Optional[GenerateConfig] = None

    @model_validator(mode="before")
    @classmethod
    def _legacy_compat(cls, values: object) -> object:
        if not isinstance(values, dict):
            return values

        cfg = values.get("config")
        if isinstance(cfg, dict):
            values.setdefault("voiceId", cfg.get("voiceId"))
            if cfg.get("speed") is not None:
                values.setdefault("speed", cfg.get("speed"))
            if cfg.get("presetKey"):
                values.setdefault("preset", cfg.get("presetKey"))
        export = values.get("export")
        if isinstance(export, dict) and export.get("format"):
            values.setdefault("exportFormat", export.get("format"))
        return values
