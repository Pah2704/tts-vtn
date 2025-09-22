# TTS-VTN – Phase 1: Nhật ký triển khai & Hướng dẫn chi tiết

## 0) Mục tiêu & phạm vi

**Mục tiêu Phase 1**
- Khóa kiến trúc & scope, dựng môi trường dev, chạy được “đầu–cuối” Single Voice (Piper).
- Có pipeline xử lý âm thanh (normalize LUFS, peak limit), hiển thị metrics (LUFS/Peak/Duration).
- Export được **MP3/WAV/FLAC/M4A**.

**Kiến trúc tổng thể**
- **Frontend**: SPA React (Vite + TS), 2 tab (hiện mới làm Single Voice).
- **Backend**: FastAPI (Python 3.11) + Piper CLI, pipeline âm thanh mô-đun.
- **Hạ tầng bổ trợ**: FFmpeg (pydub), Redis (cho phase sau), Docker Desktop (WSL integration).

**Definition of Done (Phase 1)**
- FE gọi **`POST /api/generate`**, nghe được file trả về.
- Pipeline normalize -16 LUFS + true peak limit -1 dBFS, trả metrics lên UI.
- Export hoạt động (ít nhất MP3/WAV).
- FE/BE có test cơ bản, dev server chạy ổn.
- Một số hardening bảo mật cơ bản: body limit, ẩn stacktrace, validate schema.

---

## 1) Chuẩn bị môi trường (WSL2 Ubuntu)

```bash
# Cập nhật & công cụ cơ bản
sudo apt-get update
sudo apt-get install -y build-essential curl git ca-certificates software-properties-common

# Python 3.11 + FFmpeg
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev ffmpeg

# Node LTS + pnpm (qua nvm)
export NVM_DIR="$HOME/.nvm"
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
. "$NVM_DIR/nvm.sh"
nvm install --lts
nvm use --lts
npm i -g pnpm

# Docker Desktop (trên Windows) bật WSL integration
# Redis dev container (dùng ở phase sau)
docker run -d --name tts-redis --restart unless-stopped -p 6379:6379 redis:7-alpine
2) Khởi tạo monorepo
bash
Sao chép mã
mkdir -p ~/tts-vtn && cd ~/tts-vtn
git init
pnpm init -y

# pnpm workspace (YAML, không phải JSON)
cat > pnpm-workspace.yaml <<'YAML'
packages:
  - "frontend"
  - "backend"
YAML

# Frontend (Vite + React + TS)
pnpm dlx create-vite@latest frontend -- --template react-ts
pnpm -C frontend install

# Backend skeleton
mkdir -p backend/{api,modules,jobs,core,outputs,tests,models}
python3.11 -m venv .venv && source .venv/bin/activate

cat > backend/requirements.txt <<'REQ'
fastapi
uvicorn[standard]
pydub
pyloudnorm
librosa
numpy
soundfile
celery
redis
python-multipart
pydantic-settings
httpx
pytest
REQ
pip install -r backend/requirements.txt
App FastAPI tối thiểu (để health check):

python
Sao chép mã
# backend/main.py (sau này được mở rộng: CORS, middleware, exception handler…)
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import PlainTextResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .api.routes import api_router

MAX_BODY_BYTES = 2 * 1024 * 1024  # 2MB dev

class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY_BYTES:
            return PlainTextResponse("Payload Too Large", status_code=413)
        return await call_next(request)

app = FastAPI(title="TTS-VTN")

# CORS dev (allow all)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"], max_age=86400
)
app.add_middleware(BodySizeLimitMiddleware)

@app.get("/healthz")
def healthz():
    return {"ok": True}

# Mount API routes
app.include_router(api_router, prefix="/api")

# Serve outputs/
outputs_dir = Path(__file__).resolve().parent / "outputs"
outputs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")

# JSON error chung, không rò rỉ stacktrace
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": "Internal Server Error"}, status_code=500)
3) Frontend – các types/contract (bước 4)
Mục tiêu: khóa public API FE↔BE và shape dữ liệu nội bộ FE. Chỉ có interfaces/types & signatures (không implement nặng).

frontend/src/types/api.ts

ts
Sao chép mã
export type Engine = "piper" | "xtts";
export type ExportFormat = "mp3" | "wav" | "flac" | "m4a";
export type EmotionTag = "happy" | "sad" | "excited" | "calm" | "serious" | "whisper";
export type PresetKey = "podcast_standard" | "audiobook_professional" | "announcement" | "natural_minimal";

export interface ExportOptions {
  format: ExportFormat;
  bitrateKbps?: 128 | 192 | 256 | 320;
}

export interface SynthesisConfig {
  /** Voice ID của engine (ví dụ Piper: 'vi_VN-vais1000-medium') */
  voiceId: string;
  /** Tốc độ 0.5–2.0 */
  speed?: number;
  /** Nhãn cảm xúc (chưa dùng ở Phase 1) */
  emotions?: EmotionTag[];
  /** preset xử lý (chưa dùng ở Phase 1) */
  presetKey?: PresetKey | null;
}

export interface QualityMetrics {
  lufsIntegrated: number;
  truePeakDb: number;
  durationSec: number;
}

export interface GenerateRequest {
  mode?: "sync" | "async";
  engine: Engine;
  text: string;
  config: SynthesisConfig;
  export?: ExportOptions;
}

export interface SyncGenerateResponse {
  kind: "sync";
  audioUrl: string;   // ví dụ: /outputs/<id>.mp3
  format: ExportFormat;
  metrics: QualityMetrics;
}

export interface AsyncGenerateResponse {
  kind: "async";
  jobId: string;
}
export type GenerateResponse = SyncGenerateResponse | AsyncGenerateResponse;

/** Chữ ký client FE dùng */
export type GenerateFn = (req: GenerateRequest, signal?: AbortSignal) => Promise<GenerateResponse>;
export type GetStatusFn = (jobId: string, signal?: AbortSignal) => Promise<unknown>;
export type DownloadResultFn = (jobId: string, format?: ExportFormat, signal?: AbortSignal) => Promise<Blob>;
frontend/src/types/audio.ts

ts
Sao chép mã
export interface ABItem {
  id: string;
  label: string;
  url: string;
}

export interface WaveformModel {
  /** URL audio để render waveform */
  url: string;
  /** nếu có A/B compare */
  compare?: ABItem[];
}

export interface ReaderConfig {
  voiceId: string;
  speed: number; // 0.5–2.0
  emotions?: string[];
  backgroundFx?: "none" | "rain" | "cafe" | "forest" | "ocean" | "fire" | "wind";
}
frontend/src/types/dialogue.ts

ts
Sao chép mã
export interface Character {
  id: string;
  name: string;
}

export interface Utterance {
  characterId: string;
  text: string;
  lineNo: number;
}

export interface ParsedDialogue {
  characters: Character[];
  utterances: Utterance[];
}

/**
 * Phân tích văn bản theo cú pháp:
 *   [Tên Nhân Vật]: Lời thoại
 *
 * @pre text là chuỗi UTF-8, chiều dài hợp lệ (0..~10k)
 * @post trả về danh sách nhân vật & lời thoại theo thứ tự xuất hiện
 * @throws nếu dữ liệu không phải chuỗi (TypeError)
 */
export function parseDialogue(text: string): ParsedDialogue;
4) Frontend – cấu hình & client
Cấu hình API base

bash
Sao chép mã
# frontend/.env.development
VITE_API_BASE=http://localhost:8000/api
Client FE frontend/src/api/client.ts

ts
Sao chép mã
import type {
  GenerateFn, GetStatusFn, DownloadResultFn,
  ExportFormat, GenerateResponse
} from "../types/api";

const fallbackBase = (() => {
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000/api`;
  }
  return "http://localhost:8000/api";
})();
const API_BASE = (import.meta as any).env?.VITE_API_BASE ?? fallbackBase;

const API_ORIGIN = (() => {
  try { return new URL(API_BASE).origin; } catch { return "http://localhost:8000"; }
})();

async function handleJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if ((j as any)?.detail) msg += `: ${(j as any).detail}`;
    } catch {}
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const generate: GenerateFn = async (req, signal) => {
  const res = await fetch(`${API_BASE}/generate`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify(req), signal
  });
  return handleJson<GenerateResponse>(res);
};

export const getStatus: GetStatusFn = async (jobId, signal) => {
  const res = await fetch(`${API_BASE}/status/${encodeURIComponent(jobId)}`, { signal });
  return handleJson(res);
};

export const downloadResult: DownloadResultFn = async (jobId, format: ExportFormat = "wav", signal) => {
  const res = await fetch(`${API_BASE}/result/${encodeURIComponent(jobId)}?format=${format}`, { signal });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.blob();
};

export function toBackendUrl(pathOrUrl: string): string {
  if (!pathOrUrl) return "";
  if (/^https?:\/\//i.test(pathOrUrl)) return pathOrUrl;
  const p = pathOrUrl.startsWith("/") ? pathOrUrl : `/${pathOrUrl}`;
  return `${API_ORIGIN}${p}`;
}
5) Backend – config & modules
Đọc cấu hình từ .env backend/core/config.py

python
Sao chép mã
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PIPER_BIN: str = "piper"
    PIPER_MODEL_PATH: str
    PIPER_CONFIG_PATH: str | None = None
    PIPER_TIMEOUT_SEC: int = 60

    class Config:
        env_file = "backend/.env"
        env_file_encoding = "utf-8"

settings = Settings()
TTSManager (Piper CLI) backend/modules/tts_manager.py

python
Sao chép mã
from dataclasses import dataclass
from typing import Optional, List
import os, shutil, subprocess, tempfile
from ..core.config import settings

@dataclass
class SynthesisConfig:
    voice_id: str
    speed: float = 1.0
    emotions: Optional[List[str]] = None  # chưa dùng ở Phase 1

class TTSManager:
    def __init__(self, engine: str = "piper",
                 model_path: Optional[str] = None,
                 config_path: Optional[str] = None,
                 piper_bin: Optional[str] = None) -> None:
        self.engine = engine
        self.piper_bin = piper_bin or settings.PIPER_BIN
        self.model_path = model_path or settings.PIPER_MODEL_PATH
        self.config_path = config_path or settings.PIPER_CONFIG_PATH

        if shutil.which(self.piper_bin) is None:
            raise RuntimeError("Piper binary not found.")
        if not self.model_path or not os.path.exists(self.model_path):
            raise RuntimeError("Missing PIPER_MODEL_PATH or file not found.")

    def synthesize(self, text: str, cfg: SynthesisConfig) -> bytes:
        # Piper nhận length-scale (nghịch đảo speed): length-scale = 1/speed
        length_scale = max(0.25, min(4.0, 1.0 / float(cfg.speed or 1.0)))
        cmd = [self.piper_bin, "--model", self.model_path, "--length-scale", str(length_scale)]
        if self.config_path:
            cmd += ["--config", self.config_path]

        proc = subprocess.run(
            cmd, input=text.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=settings.PIPER_TIMEOUT_SEC
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Piper failed: {proc.stderr.decode('utf-8', 'ignore')[:200]}")
        return proc.stdout  # WAV bytes
Quality metrics backend/modules/quality_control.py

python
Sao chép mã
from typing import TypedDict
import io, numpy as np, soundfile as sf
import pyloudnorm as pyln

class MetricsDict(TypedDict):
    lufsIntegrated: float
    truePeakDb: float
    durationSec: float

def _read_wav_bytes(wav_bytes: bytes):
    bio = io.BytesIO(wav_bytes)
    data, sr = sf.read(bio, always_2d=True)
    return data, sr

def measure_metrics(wav_bytes: bytes) -> MetricsDict:
    data, sr = _read_wav_bytes(wav_bytes)
    meter = pyln.Meter(sr)
    lufs = float(meter.integrated_loudness(data))
    peak = float(np.max(np.abs(data)))
    eps = 1e-12
    peak_db = 20.0 * np.log10(max(peak, eps))
    duration = float(data.shape[0]) / float(sr)
    return {"lufsIntegrated": lufs, "truePeakDb": peak_db, "durationSec": duration}
Audio pipeline backend/modules/audio_pipeline.py

python
Sao chép mã
from typing import Tuple
import io, numpy as np, soundfile as sf
import pyloudnorm as pyln
from .quality_control import measure_metrics, MetricsDict

def _read_wav_bytes(wav_bytes: bytes):
    bio = io.BytesIO(wav_bytes); data, sr = sf.read(bio, always_2d=True); return data, sr
def _write_wav_bytes(data, sr) -> bytes:
    bio = io.BytesIO(); sf.write(bio, data, sr, format="WAV"); return bio.getvalue()

def normalize_to_lufs(wav_bytes: bytes, target_lufs: float = -16.0) -> bytes:
    data, sr = _read_wav_bytes(wav_bytes)
    meter = pyln.Meter(sr)
    loudness = meter.integrated_loudness(data)
    gain_db = float(target_lufs - loudness)
    gain = 10.0 ** (gain_db / 20.0)
    data2 = np.clip(data * gain, -1.0, 1.0)
    return _write_wav_bytes(data2, sr)

def peak_limit(wav_bytes: bytes, ceiling_db: float = -1.0) -> bytes:
    data, sr = _read_wav_bytes(wav_bytes)
    ceiling_amp = 10.0 ** (ceiling_db / 20.0)
    data2 = np.clip(data, -ceiling_amp, ceiling_amp)
    return _write_wav_bytes(data2, sr)

def run_pipeline(wav_bytes: bytes) -> Tuple[bytes, MetricsDict]:
    x = normalize_to_lufs(wav_bytes, -16.0)
    y = peak_limit(x, -1.0)
    metrics: MetricsDict = measure_metrics(y)
    return y, metrics
API routes backend/api/routes.py (DTO + handler đồng bộ Piper)

python
Sao chép mã
from typing import List, Literal, Optional, Union, Annotated
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from pathlib import Path
import io, uuid
from pydub import AudioSegment

Engine = Literal["piper", "xtts"]
ExportFormat = Literal["mp3", "wav", "flac", "m4a"]
PresetKey = Literal["podcast_standard", "audiobook_professional", "announcement", "natural_minimal"]
EmotionTag = Literal["happy", "sad", "excited", "calm", "serious", "whisper"]
Text5k = Annotated[str, StringConstraints(min_length=1, max_length=5000, strip_whitespace=True)]

class QualityMetrics(BaseModel):
    lufsIntegrated: float; truePeakDb: float; durationSec: float

class ExportOptions(BaseModel):
    format: ExportFormat
    bitrateKbps: Optional[Literal[128, 192, 256, 320]] = None

class SynthesisConfig(BaseModel):
    voiceId: str
    speed: Optional[float] = Field(default=1.0, ge=0.5, le=2.0)
    emotions: Optional[List[EmotionTag]] = None
    presetKey: Optional[PresetKey] = None

class GenerateRequest(BaseModel):
    mode: Optional[Literal["sync", "async"]] = "sync"
    engine: Engine
    text: Text5k
    config: SynthesisConfig
    export: Optional[ExportOptions] = None

class SyncGenerateResponse(BaseModel):
    kind: Literal["sync"] = "sync"
    audioUrl: str; format: ExportFormat; metrics: QualityMetrics

class AsyncGenerateResponse(BaseModel):
    kind: Literal["async"] = "async"; jobId: str

GenerateResponse = Union[SyncGenerateResponse, AsyncGenerateResponse]
api_router = APIRouter(tags=["tts"])

OUTPUT_DIR = (Path(__file__).resolve().parent.parent / "outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from ..modules.tts_manager import TTSManager, SynthesisConfig as EngineCfg
from ..modules.audio_pipeline import run_pipeline
from ..modules.quality_control import MetricsDict

@api_router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    if req.mode != "sync":
        raise HTTPException(status_code=400, detail="Only sync mode supported in Phase 1.")
    if req.engine != "piper":
        raise HTTPException(status_code=400, detail="Only engine 'piper' supported in Phase 1.")

    text: str = req.text
    speed = float(req.config.speed or 1.0)

    # (1) TTS -> WAV
    tts = TTSManager(engine="piper")
    raw_wav = tts.synthesize(text, EngineCfg(voice_id=req.config.voiceId, speed=speed, emotions=req.config.emotions))

    # (2) Pipeline -> WAV processed + metrics
    processed_wav, metrics = run_pipeline(raw_wav)
    m: MetricsDict = metrics

    # (3) Export
    fmt: ExportFormat = req.export.format if req.export else "wav"
    bitrate = f"{req.export.bitrateKbps}k" if req.export and req.export.bitrateKbps else None

    audio: AudioSegment = AudioSegment.from_file(io.BytesIO(processed_wav), format="wav")
    job_id = uuid.uuid4().hex
    out_path = OUTPUT_DIR / f"{job_id}.{fmt}"
    if fmt == "wav":
        audio.export(out_path, format="wav")
    elif fmt in ("mp3", "flac", "m4a"):
        audio.export(out_path, format=fmt, bitrate=bitrate)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")

    return SyncGenerateResponse(
        audioUrl=f"/outputs/{out_path.name}",
        format=fmt,
        metrics=QualityMetrics(**m),
    )
6) Cài Piper & giọng, cấu hình .env backend
bash
Sao chép mã
# ví dụ lưu ở ~/piper/voices/vi_VN/
mkdir -p ~/piper/voices/vi_VN
# tải 2 file:
#  - vi_VN-vais1000-medium.onnx
#  - vi_VN-vais1000-medium.onnx.json

# backend/.env (đường dẫn tuyệt đối, KHÔNG dùng $USER)
cat > backend/.env <<'ENV'
PIPER_BIN=piper
PIPER_MODEL_PATH=/home/<YOUR_USER>/piper/voices/vi_VN/vi_VN-vais1000-medium.onnx
PIPER_CONFIG_PATH=/home/<YOUR_USER>/piper/voices/vi_VN/vi_VN-vais1000-medium.onnx.json
PIPER_TIMEOUT_SEC=60
ENV
7) Chạy dev
Backend

bash
Sao chép mã
source .venv/bin/activate
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 --env-file backend/.env
Frontend

bash
Sao chép mã
cd frontend
pnpm dev
# mở http://localhost:5173 (UI Single Voice)
Curl thử

bash
Sao chép mã
curl -s -X POST 'http://localhost:8000/api/generate' \
  -H 'content-type: application/json' \
  -d '{"mode":"sync","engine":"piper","text":"Xin chào!","config":{"voiceId":"vi_VN-vais1000-medium","speed":1.0},"export":{"format":"mp3"}}' | jq .
8) Unit tests
Backend (pytest)

quality_control đo metrics hợp lệ.

audio_pipeline normalize ±1 LU quanh -16 LUFS, peak ≤ -1 dBFS.

/api/generate “happy path” mock Piper (monkeypatch TTSManager.__init__ + synthesize).

Trường hợp speed out-of-range → 422 (vi phạm schema).

Chạy:

bash
Sao chép mã
source .venv/bin/activate
PYTHONPATH=. pytest -q
Frontend (Vitest)

src/__tests__/client.spec.ts: export hàm generate/getStatus/downloadResult.

src/__tests__/parser.spec.ts: parseDialogue stub trả cấu trúc hợp lệ.

Chạy:

bash
Sao chép mã
pnpm -C frontend test
pnpm -C frontend exec tsc --noEmit
9) Hardening & chất lượng mã
pydantic-settings (backend/core/config.py) đọc .env, có PIPER_TIMEOUT_SEC.

CORS dev allow all, tránh lỗi “Failed to fetch” khi FE chạy ở localhost/127.0.0.1/IP LAN.

Body size limit 2MB (middleware).

Exception handler trả JSON gọn 500, không rò rỉ stacktrace.

Schema validation sớm:

text: 1..5000, strip_whitespace=True (dùng Annotated[str, StringConstraints]).

speed: [0.5, 2.0].

TypedDict cho metrics (MetricsDict), stubs cho pydub (thư mục typings/pydub) để Pylance hiểu AudioSegment.

Static outputs: ghi cố định vào backend/outputs rồi mount /outputs → tránh path traversal.

10) IDE/Pylance: các chỉnh sửa để hết cảnh báo “Unknown”
Tránh dùng constr(...) trực tiếp trong annotation → chuyển sang
Annotated[str, StringConstraints(min_length=1, max_length=5000, strip_whitespace=True)].

Metrics dùng TypedDict (MetricsDict) để type-safe.

Thêm type stubs cho pydub:

bash
Sao chép mã
typings/pydub/__init__.pyi
typings/pydub/audio_segment.pyi
Annotate middleware & exception handler:

dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response

unhandled_exception_handler(...) -> JSONResponse

11) CI (tạm dừng)
Đã khởi tạo 2 workflow:

ci.yml (backend pytest + ruff; frontend tsc + vitest).

preview.yml (build FE, upload artifact).

Ghi chú: runner GitHub đôi lúc lỗi lookup pnpm. Phương án dùng Corepack + cache pnpm store đã thiết lập; có thể cần tinh chỉnh thêm nếu muốn bật CI lại sau.

12) Troubleshooting
500 / Missing PIPER_MODEL_PATH
backend/.env phải dùng đường dẫn tuyệt đối; chạy uvicorn với --env-file backend/.env.

UI “Failed to fetch”
Backend chưa chạy; hoặc CORS. Dev đã allow_origins=["*"]. Xem tab Network của DevTools.

422
Vi phạm schema (text rỗng/quá dài, speed ngoài 0.5–2.0).

jq: parse error
Backend trả HTML (lỗi 500). Dùng:

bash
Sao chép mã
curl ... -o /tmp/resp.json -w '\nHTTP %{http_code}\n'
cat /tmp/resp.json
Piper CLI test nhanh:

bash
Sao chép mã
echo "Xin chào Piper" | piper --model "$PIPER_MODEL_PATH" \
    --config "$PIPER_CONFIG_PATH" --length-scale 1.0 --output_file /tmp/piper_test.wav
13) Roadmap ngắn (tiếp theo)
Parser + Multi-Voice tab: implement parseDialogue chuẩn [Tên]: Lời thoại, sinh scene & A/B compare.

Async queue: Celery + Redis; /status, /result, streaming progress.

DB + migration: SQLModel/Alembic — jobs, artifacts, presets.

CI xanh: hoàn thiện workflow, cache hợp lý, badge vào README.

Tối ưu: cache voice, profile synth/FFmpeg/LUFS; giảm latency.

14) Phụ lục lệnh nhanh
bash
Sao chép mã
# Start backend (dev)
source .venv/bin/activate
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 --env-file backend/.env

# Start frontend (dev)
pnpm -C frontend dev

# FE typecheck & tests
pnpm -C frontend exec tsc --noEmit
pnpm -C frontend test

# BE tests
PYTHONPATH=. pytest -q

# Redis container (dev)
docker start tts-redis || docker run -d --name tts-redis --restart unless-stopped -p 6379:6379 redis:7-alpine
