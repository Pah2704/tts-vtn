from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import PlainTextResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .api.routes import api_router

MAX_BODY_BYTES = 2 * 1024 * 1024  # 2MB cho dev

class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY_BYTES:
            return PlainTextResponse("Payload Too Large", status_code=413)
        return await call_next(request)

app = FastAPI(title="TTS-VTN")

# CORS: DEV ONLY — allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=86400,
)
app.add_middleware(BodySizeLimitMiddleware)

@app.get("/healthz")
def healthz():
    return {"ok": True}

# Mount API routes
app.include_router(api_router, prefix="/api")

# Serve outputs as static
outputs_dir = Path(__file__).resolve().parent / "outputs"
outputs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")

# Return JSON gọn cho lỗi không phải HTTPException
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": "Internal Server Error"}, status_code=500)
