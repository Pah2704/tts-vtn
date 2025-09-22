# TTS-VTN — Phase 1

Text-to-Speech (Tiếng Việt) theo kiến trúc **SPA React ↔ FastAPI + Piper** với pipeline xử lý audio (normalize LUFS, peak limit) và **quality metrics (LUFS/Peak/Duration)**. Repo dạng **monorepo** (pnpm workspaces).

---

## 🚩 Tính năng Phase 1
- UI **Single Voice** (Piper) – nhập text → synth → nghe ngay.
- `/api/generate` (sync) → xuất **MP3/WAV/FLAC/M4A** + metrics.
- Pipeline tối thiểu: **normalize -16 LUFS** + **true-peak limit -1 dBFS**.
- Serve file qua `/outputs/<id>.<ext>`.
- FE/BE tests cơ bản (Vitest + Pytest).

---

## 🧭 Kiến trúc (Mermaid)

```mermaid
flowchart LR
A[React SPA (Vite)] -- POST /api/generate --> B(FastAPI)
B --> C[TTSManager (Piper CLI)]
C -->|WAV| D[Audio Pipeline<br/>normalize/limit]
D -->|WAV| E[pydub/ffmpeg export]
E -->|file| F[backend/outputs/]
F -->|/outputs/...| A
📁 Cấu trúc chính
bash
Sao chép mã
tts-vtn/
├── frontend/               # Vite + React + TS
│   └── src/
│       ├── api/            # client gọi backend
│       ├── app/            # SingleVoice page
│       ├── components/     # Player skeleton
│       ├── lib/            # parser stub
│       └── types/          # contracts FE
├── backend/                # FastAPI
│   ├── api/routes.py       # /api/generate
│   ├── modules/            # tts_manager, audio_pipeline, quality_control
│   ├── core/config.py      # pydantic-settings
│   ├── outputs/            # artifacts xuất ra (static)
│   └── tests/              # pytest
└── typings/pydub/          # type stubs cho Pylance
🔧 Yêu cầu môi trường (WSL2 Ubuntu khuyến nghị)
Node LTS + pnpm

Python 3.11+

FFmpeg (pydub dùng)

Docker Desktop (WSL integration on) để chạy Redis (cho phase sau)

Piper (pip install piper-tts) + giọng .onnx + .onnx.json

🚀 Quickstart
1) Cài & chuẩn bị (một lần)
bash
Sao chép mã
# Python venv & backend deps
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# Tải voice (ví dụ vi_VN-vais1000-medium)
mkdir -p ~/piper/voices/vi_VN
# tải 2 file .onnx và .onnx.json từ HuggingFace (xem doc dự án Piper)
# ... (bạn đã tải ở bước trước)

# Khai báo env cho backend
cat > backend/.env <<'ENV'
PIPER_BIN=piper
PIPER_MODEL_PATH=/home/<YOUR_USER>/piper/voices/vi_VN/vi_VN-vais1000-medium.onnx
PIPER_CONFIG_PATH=/home/<YOUR_USER>/piper/voices/vi_VN/vi_VN-vais1000-medium.onnx.json
PIPER_TIMEOUT_SEC=60
ENV

# Frontend deps
pnpm -C frontend install
⚠️ Không dùng $USER trong .env – ghi đường dẫn tuyệt đối.

2) Chạy dev
Terminal A — Backend:

bash
Sao chép mã
source .venv/bin/activate
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 --env-file backend/.env
Terminal B — Frontend:

bash
Sao chép mã
cd frontend
pnpm dev
# mở http://localhost:5173
Dev CORS đang allow all origins để tiện thử nghiệm.

🔌 API
POST /api/generate (sync, Phase 1)
Request body

json
Sao chép mã
{
  "mode": "sync",
  "engine": "piper",
  "text": "Xin chào...",
  "config": { "voiceId": "vi_VN-vais1000-medium", "speed": 1.0 },
  "export": { "format": "mp3", "bitrateKbps": 192 }
}
text: 1..5000 ký tự (strip whitespace)

speed: 0.5..2.0

format: mp3|wav|flac|m4a

Response 200 (sync)

json
Sao chép mã
{
  "kind": "sync",
  "audioUrl": "/outputs/<id>.mp3",
  "format": "mp3",
  "metrics": { "lufsIntegrated": -16.02, "truePeakDb": -0.99, "durationSec": 2.97 }
}
Curl ví dụ

bash
Sao chép mã
curl -s -X POST 'http://localhost:8000/api/generate' \
  -H 'content-type: application/json' \
  -d '{"mode":"sync","engine":"piper","text":"Xin chào!","config":{"voiceId":"vi_VN-vais1000-medium","speed":1.0},"export":{"format":"mp3"}}'
Static files
/outputs được mount static: mở http://localhost:8000/outputs/<id>.mp3.

🧪 Test & Typecheck
Backend:

bash
Sao chép mã
source .venv/bin/activate
PYTHONPATH=. pytest -q
Frontend:

bash
Sao chép mã
pnpm -C frontend test
pnpm -C frontend exec tsc --noEmit
🔒 Bảo mật & Ràng buộc hiện có
Body limit: 2MB (middleware).

Ẩn stacktrace – lỗi không phải HTTPException trả {"detail":"Internal Server Error"}.

Validate sớm bằng schema:

text: 1..5000, strip whitespace.

speed: 0.5..2.0.

Export chỉ cho phép mp3|wav|flac|m4a.

Outputs ghi dưới backend/outputs (đường dẫn cố định, tránh traversal).

⚠️ Known issues / Troubleshooting
500 “Missing PIPER_MODEL_PATH”
→ .env sai đường dẫn tuyệt đối; chạy lại server với --env-file backend/.env.

“Failed to fetch” từ UI
→ Backend chưa chạy, hoặc CORS. Dev đã allow *; kiểm tra DevTools/Network.

422 Unprocessable Entity
→ Vi phạm schema (text rỗng/quá dài, speed ngoài [0.5,2.0]).

pydub/ffmpeg lỗi
→ Cài FFmpeg (sudo apt-get install -y ffmpeg).

Test BE báo thiếu httpx
→ pip install -r backend/requirements.txt (có httpx).

jq parse error khi thử curl
→ Backend trả HTML (lỗi 500). In thẳng body: curl ... -o /tmp/resp.json -w '\nHTTP %{http_code}\n'.

✅ Definition of Done (Phase 1)
Single Voice (Piper): nhập text → synth → nghe.

Pipeline: normalize LUFS + peak limit, metrics trả về UI.

Export MP3/WAV hoạt động.

Tests cơ bản pass (FE/BE).

Bảo mật cơ bản: giới hạn input, ẩn stacktrace, body limit.

Quickstart/Docs sẵn sàng.

🗺️ Roadmap ngắn
Parser + Multi-Voice tab: detect [Tên]: Lời thoại, chia scene.

/status & queue (Celery + Redis) cho async.

DB (SQLModel + Alembic): jobs/artifacts/presets.

CI (GitHub Actions): lint/test/build matrix Node 18/20 + Python.

Tối ưu hiệu năng: cache voice, profiling IO/FFmpeg.

📄 Ghi chú dev
Thư mục typings/pydub/ chứa type stubs nhỏ để Pylance nhận diện AudioSegment.

backend/core/config.py dùng pydantic-settings đọc .env; hỗ trợ PIPER_TIMEOUT_SEC.

