from typing import List, Literal, Optional, Union, Annotated
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from pathlib import Path
import io, uuid
from pydub import AudioSegment

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


@api_router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    """Phase 1: sync với Piper, trả file đã xử lý + metrics."""
    if req.mode != "sync":
        raise HTTPException(status_code=400, detail="Only sync mode supported in Phase 1.")
    if req.engine != "piper":
        raise HTTPException(status_code=400, detail="Only engine 'piper' supported in Phase 1.")

    text: str = req.text  # đã strip/validate bởi schema
    speed = float(req.config.speed or 1.0)

    # 1) TTS -> WAV
    tts = TTSManager(engine="piper")
    raw_wav = tts.synthesize(text, EngineCfg(voice_id=req.config.voiceId, speed=speed, emotions=req.config.emotions))

    # 2) Pipeline -> WAV processed + metrics
    processed_wav, metrics = run_pipeline(
        raw_wav,
        preset_key=req.config.presetKey,   # ← nhận từ FE
    )  
    m: MetricsDict = metrics

    # 3) Export
    fmt: ExportFormat = req.export.format if req.export else "wav"
    bitrate = f"{req.export.bitrateKbps}k" if req.export and req.export.bitrateKbps else None

    # nhờ stub typings/pydub, Pylance hiểu đúng kiểu AudioSegment
    audio: AudioSegment = AudioSegment.from_file(io.BytesIO(processed_wav), format="wav")
    job_id = uuid.uuid4().hex
    out_path = OUTPUT_DIR / f"{job_id}.{fmt}"
    if fmt == "wav":
        audio.export(str(out_path), format="wav")                # ✅ Path → str
    elif fmt in ("mp3", "flac", "m4a"):
        audio.export(str(out_path), format=fmt, bitrate=bitrate) # ✅ Path → str
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
    raise HTTPException(status_code=501, detail=f"Not implemented: /status/{job_id}")


@api_router.get("/presets", response_model=List[PresetInfo])
def list_presets():
    return [{
        "key": p["key"],
        "title": p["title"],
        "lufsTarget": p["dsp"]["lufs_target"],
        "description": p.get("description","")
    } for p in PRESETS.values()]