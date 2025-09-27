from pathlib import Path
import os
import logging
import mimetypes
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import PlainTextResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from backend.routes import health, voices, history, presets_user
from backend.routes import generate as generate_route
from backend.routes.presets import router as presets_router
from .modules.tts_manager import (
    TTSManager,
    PiperConfigError,
    set_piper_health,
    get_piper_health,
)

MAX_BODY_BYTES = 2 * 1024 * 1024  # 2MB cho dev

mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("audio/flac", ".flac")
mimetypes.add_type("audio/ogg", ".ogg")

OUTPUTS_DIR = Path(os.getenv("OUTPUTS_DIR", "backend/outputs")).resolve()

logger = logging.getLogger(__name__)

class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY_BYTES:
            return PlainTextResponse("Payload Too Large", status_code=413)
        return await call_next(request)

@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        manager = TTSManager(engine="piper")
        manager.validate_runtime()
    except PiperConfigError as exc:
        set_piper_health(False, str(exc))
        logger.warning("Piper startup check failed: %s", exc)
    except Exception as exc:  # pragma: no cover
        set_piper_health(False, f"Unexpected Piper startup failure: {exc}")
        logger.exception("Unexpected error during Piper startup check")
    else:
        set_piper_health(True, None)
    yield


app = FastAPI(title="TTS-VTN Local", lifespan=lifespan)

allow_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,*")
allow_origins = [origin.strip() for origin in allow_origins_env.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Range"],
    expose_headers=["Content-Range", "Accept-Ranges"],
    max_age=3600,
)
app.add_middleware(BodySizeLimitMiddleware)

@app.get("/healthz")
def healthz() -> dict[str, object]:
    ready, error = get_piper_health()
    return {"ok": True, "piperReady": ready, "piperError": error}


@app.get("/readyz")
def readyz() -> JSONResponse:
    ready, error = get_piper_health()
    payload = {"ok": ready, "piperReady": ready, "piperError": error}
    status_code = 200 if ready else 503
    return JSONResponse(status_code=status_code, content=payload)

# Routers
app.include_router(health.router, prefix="")
app.include_router(generate_route.router, prefix="")
app.include_router(presets_router, prefix="")
app.include_router(voices.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(presets_user.router, prefix="/api")

# Serve outputs as static
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR), check_dir=False), name="outputs")

# Serve FE build (frontend/dist) tại root "/"
fe_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if fe_dist.exists():
    app.mount("/", StaticFiles(directory=str(fe_dist), html=True), name="fe")

# Accept-Ranges header for static audio
@app.middleware("http")
async def add_accept_ranges(request: Request, call_next: RequestResponseEndpoint) -> Response:  # type: ignore[override]
    response = await call_next(request)
    if request.url.path.startswith("/outputs/"):
        response.headers.setdefault("Accept-Ranges", "bytes")
        response.headers.setdefault("Cache-Control", "public, max-age=0, must-revalidate")
    return response


# Return JSON gọn cho lỗi không phải HTTPException
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": "Internal Server Error"}, status_code=500)
