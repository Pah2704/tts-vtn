# backend/api/routes.py
from typing import List, Literal, Optional, Union, Annotated, Dict, Any
from pathlib import Path
import io
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from celery.result import AsyncResult
from pydub import AudioSegment

from backend.tasks import generate_task  # Celery task

# ==== Types khớp FE ====

Engine = Literal["piper", "xtts"]
ExportFormat = Literal["mp3", "wav", "flac", "m4a"]
PresetKey = Literal["podcast_standard", "audiobook_professional", "announcement", "natural_minimal"]
EmotionTag = Literal["happy", "sad", "excited", "calm", "serious", "whisper"]
BackgroundFx = Literal["none", "rain", "cafe", "forest", "ocean", "fire", "wind"]

# Chuỗi 1..5000 ký tự, strip whitespace
Text5k = Annotated[str, StringConstraints(min_length=1, max_length=5000, strip_whitespace=True)]

class QualityMetrics(BaseModel):
    lufsIntegrated: float
    truePeakDb: float
    durationSec: float
    # Phase 2 (optional)
    rms: Optional[float] = None
    crestFactor: Optional[float] = None
    snrApprox: Optional[float] = None
    clippingCount: Optional[int] = None
    silenceGapsMs: Optional[List[int]] = None
    qualityScore: Optional[int] = None
    warnings: Optional[List[str]] = None

class ExportOptions(BaseModel):
    format: ExportFormat
    bitrateKbps: Optional[Literal[128, 192, 256, 320]] = None

class BackgroundCfg(BaseModel):
    kind: BackgroundFx
    gain: Optional[float] = Field(default=None, ge=0.0, le=0.5)

class SynthesisConfig(BaseModel):
    voiceId: str
    speed: Optional[float] = Field(default=1.0, ge=0.5, le=2.0)
    emotions: Optional[List[EmotionTag]] = None
    background: Optional[BackgroundCfg] = None
    presetKey: Optional[PresetKey] = None

class GenerateRequest(BaseModel):
    mode: Optional[Literal["sync", "async"]] = "sync"
    engine: Engine
    text: Text5k
    config: SynthesisConfig
    export: Optional[ExportOptions] = None

class SyncGenerateResponse(BaseModel):
    kind: Literal["sync"] = "sync"
    audioUrl: str
    format: ExportFormat
    metrics: QualityMetrics

class AsyncGenerateResponse(BaseModel):
    kind: Literal["async"] = "async"
    jobId: str

GenerateResponse = Union[SyncGenerateResponse, AsyncGenerateResponse]
JobState = Literal["queued", "processing", "done", "error"]

class ErrorInfo(BaseModel):
    code: str
    message: str

class JobStatusResponse(BaseModel):
    jobId: str
    state: JobState
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    error: Optional[ErrorInfo] = None
    result: Optional[SyncGenerateResponse] = None

class PresetInfo(BaseModel):
    key: PresetKey
    title: str
    lufsTarget: float
    description: Optional[str] = None

# ==== Router & Services ====
api_router = APIRouter(tags=["tts"])

OUTPUT_DIR = (Path(__file__).resolve().parent.parent / "outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from ..modules.tts_manager import TTSManager, SynthesisConfig as EngineCfg
from ..modules.audio_pipeline import run_pipeline
from ..modules.quality_control import MetricsDict
from backend.modules.presets import PRESETS

# Map trạng thái Celery -> JobState (Literal)
def _map_state(celery_state: str) -> JobState:
    cs = (celery_state or "").upper()
    if cs in ("PENDING", "RECEIVED", "REVOKED"):
        return "queued"
    if cs in ("STARTED", "PROGRESS", "RETRY"):
        return "processing"
    if cs in ("SUCCESS",):
        return "done"
    if cs in ("FAILURE",):
        return "error"
    return "processing"

@api_router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    """
    Sync (giữ nguyên Phase 1) + nhánh async (enqueue Celery).
    """
    # Nhánh ASYNC cho Phase 3
    if req.mode == "async":
        async_result = generate_task.delay(req.model_dump())
        return AsyncGenerateResponse(kind="async", jobId=async_result.id)

    # === Nhánh SYNC hiện có (Phase 1) ===
    if req.engine != "piper":
        raise HTTPException(status_code=400, detail="Only engine 'piper' supported in Phase 1.")

    text: str = req.text
    speed = float(req.config.speed or 1.0)

    # 1) TTS -> WAV
    tts = TTSManager(engine="piper")
    raw_wav = tts.synthesize(text, EngineCfg(voice_id=req.config.voiceId, speed=speed, emotions=req.config.emotions))

    # 2) Pipeline -> WAV processed + metrics
    processed_wav, metrics = run_pipeline(
        raw_wav,
        preset_key=req.config.presetKey,
    )
    m: MetricsDict = metrics

    # 3) Export
    fmt: ExportFormat = req.export.format if req.export else "wav"
    bitrate = f"{req.export.bitrateKbps}k" if req.export and req.export.bitrateKbps else None

    audio: AudioSegment = AudioSegment.from_file(io.BytesIO(processed_wav), format="wav")
    job_id = uuid.uuid4().hex
    out_path = OUTPUT_DIR / f"{job_id}.{fmt}"
    if fmt == "wav":
        audio.export(str(out_path), format="wav")
    elif fmt in ("mp3", "flac", "m4a"):
        audio.export(str(out_path), format=fmt, bitrate=bitrate)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")

    audio_url = f"/outputs/{out_path.name}"
    return SyncGenerateResponse(
        audioUrl=audio_url,
        format=fmt,
        metrics=QualityMetrics(**m)
    )

@api_router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_status(job_id: str) -> JobStatusResponse:
    res = AsyncResult(job_id)
    mapped: JobState = _map_state(res.state)
    meta: Dict[str, Any] = res.info if isinstance(res.info, dict) else {}
    prog = meta.get("progress")
    progress: Optional[int] = int(prog) if isinstance(prog, (int, float)) else None

    if mapped == "error":
        detail = str(meta) if meta else "Unknown error"
        return JobStatusResponse(
            jobId=job_id,
            state=mapped,
            progress=progress,
            error=ErrorInfo(code="WORKER_ERROR", message=detail)
        )

    return JobStatusResponse(
        jobId=job_id,
        state=mapped,
        progress=progress
    )

@api_router.get("/result/{job_id}", response_model=SyncGenerateResponse)
async def get_result(job_id: str) -> SyncGenerateResponse:
    res = AsyncResult(job_id)
    if res.state != "SUCCESS":
        raise HTTPException(status_code=404, detail="Result not ready")

    data: Dict[str, Any] = res.result or {}

    # Bảo đảm audio_url là str (để Pylance hài lòng và tránh lỗi runtime)
    audio_url_val = data.get("audio_url")
    if not isinstance(audio_url_val, str):
        raise HTTPException(status_code=500, detail="Malformed worker result: 'audio_url' must be str")

    fmt_raw = data.get("format")
    fmt: ExportFormat = fmt_raw if fmt_raw in ("mp3", "wav", "flac", "m4a") else "wav"

    metrics_raw = data.get("metrics") or {}
    if not isinstance(metrics_raw, dict):
        raise HTTPException(status_code=500, detail="Malformed worker result: 'metrics' must be object")

    return SyncGenerateResponse(
        kind="sync",
        audioUrl=audio_url_val,
        format=fmt,
        metrics=QualityMetrics(**metrics_raw)
    )

@api_router.get("/presets", response_model=List[PresetInfo])
def list_presets():
    return [{
        "key": p["key"],
        "title": p["title"],
        "lufsTarget": p["dsp"]["lufs_target"],
        "description": p.get("description", "")
    } for p in PRESETS.values()]
