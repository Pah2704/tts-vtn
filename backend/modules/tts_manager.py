"""
TTS Manager — Piper (CLI) + XTTS (stub) adapter.

- Piper:
  - Đọc env PIPER_BIN, PIPER_MODEL_PATH, PIPER_CONFIG_PATH từ settings.
  - Map speed 0.5–2.0 -> --length_scale = 1/speed.
- XTTS (Phase 3):
  - Tự phát hiện GPU qua torch.cuda.
  - Giới hạn 2000 ký tự (ném ValueError nếu vượt).
  - Stub synthesize: tạo WAV im lặng đủ để đi qua pipeline & test.
    (Sau này thay bằng model XTTS thật.)
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List, Literal
import os
import shutil
import subprocess
import tempfile
import io

from ..core.config import settings

# Torch là optional; tắt cảnh báo Pylance khi không cài.
try:
    import torch  # type: ignore[reportMissingImports]
except Exception:
    torch = None  # type: ignore[assignment]

from pydub import AudioSegment

# ==== Hằng số / types cho XTTS ====
MAX_XTTS_CHARS = 2000
EmotionTag = Literal["happy", "sad", "excited", "calm", "serious", "whisper"]


def pick_device() -> str:
    """Trả 'cuda' nếu GPU khả dụng, ngược lại 'cpu'."""
    try:
        if torch is not None and hasattr(torch, "cuda") and torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _make_silence_ms(ms: int, frame_rate: int = 16000) -> AudioSegment:
    """
    Tạo AudioSegment im lặng.
    - Ưu tiên dùng AudioSegment.silent (nếu có).
    - Fallback: tạo WAV im lặng bằng wave + BytesIO, rồi đọc bằng from_file.
    """
    if hasattr(AudioSegment, "silent"):
        return AudioSegment.silent(duration=ms, frame_rate=frame_rate)  # type: ignore[attr-defined]

    # Fallback an toàn: dựng WAV 16-bit mono im lặng
    import wave
    num_samples = int(ms * frame_rate / 1000)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)       # 16-bit
        wf.setframerate(frame_rate)
        wf.writeframes(b"\x00\x00" * num_samples)
    buf.seek(0)
    return AudioSegment.from_file(buf, format="wav")

@dataclass(frozen=True)
class SynthesisConfig:
    voice_id: str
    speed: float = 1.0
    emotions: Optional[List[EmotionTag]] = None  # Piper CLI chưa dùng; để future


class TTSManager:
    def __init__(
        self,
        engine: str = "piper",
        model_path: Optional[str] = None,
        config_path: Optional[str] = None,
        piper_bin: Optional[str] = None,
    ) -> None:
        self.engine = engine

        # Chỉ validate Piper khi engine == "piper"
        self.piper_bin = piper_bin or settings.PIPER_BIN
        self.model_path = model_path or settings.PIPER_MODEL_PATH
        self.config_path = config_path or settings.PIPER_CONFIG_PATH

        if self.engine == "piper":
            if shutil.which(self.piper_bin) is None:
                raise RuntimeError(
                    "Piper binary not found. Ensure PIPER_BIN in PATH or set env PIPER_BIN."
                )
            if not self.model_path or not os.path.exists(self.model_path):
                raise RuntimeError("Missing PIPER_MODEL_PATH or file not found.")
            # config có thể thiếu với 1 số model, nhưng khuyến nghị có:
            if self.config_path and (not os.path.exists(self.config_path)):
                raise RuntimeError("PIPER_CONFIG_PATH set but file not found.")

    # ==== Public API ====
    def synthesize(self, text: str, cfg: SynthesisConfig) -> bytes:
        """
        PRE: text != "" (trim); 0.5 <= cfg.speed <= 2.0
        POST: trả WAV bytes.
        ERROR: ValueError input; RuntimeError khi Piper CLI lỗi.
        """
        if self.engine == "xtts":
            return self._synthesize_xtts(text, cfg)
        # Mặc định Piper
        return self._synthesize_piper(text, cfg)

    # ==== Implementations ====
    def _synthesize_xtts(self, text: str, cfg: SynthesisConfig) -> bytes:
        """
        XTTS (stub):
        - Giới hạn 2000 ký tự (ValueError nếu vượt).
        - Tạo WAV im lặng (16kHz) độ dài xấp xỉ theo độ dài text.
        - Sau này thay bằng model XTTS thật (dựa trên pick_device()).
        """
        txt = (text or "").strip()
        if not txt:
            raise ValueError("text is empty")
        if len(txt) > MAX_XTTS_CHARS:
            raise ValueError(f"XTTS text limit exceeded ({len(txt)} > {MAX_XTTS_CHARS})")

        # (Khi tích hợp model thật, dùng pick_device() để chọn 'cuda'/'cpu')
        # device = pick_device()

        # Stub: tạo WAV im lặng đủ đi pipeline
        dur_ms = max(300, min(6000, int(len(txt) * 1.2)))  # xấp xỉ 0.3–6.0s
        seg = _make_silence_ms(dur_ms, frame_rate=16000)
        buf = io.BytesIO()
        seg.export(buf, format="wav")
        return buf.getvalue()

    def _synthesize_piper(self, text: str, cfg: SynthesisConfig) -> bytes:
        """
        Piper CLI:
        - Map speed -> length_scale = 1/speed.
        - Đọc model/config từ settings.
        """
        txt = (text or "").strip()
        if not txt:
            raise ValueError("text is empty")
        sp = float(cfg.speed)
        if not (0.5 <= sp <= 2.0):
            raise ValueError("speed out of range [0.5,2.0]")

        length_scale = 1.0 / sp

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            cmd = [
                self.piper_bin,
                "--model",
                self.model_path,
                "--output_file",
                tmp_path,
                "--length-scale",
                f"{length_scale:.3f}",
            ]
            if self.config_path:
                cmd += ["--config", self.config_path]

            # Piper đọc text từ stdin
            proc = subprocess.run(
                cmd,
                input=txt.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=settings.PIPER_TIMEOUT_SEC,
            )
            if proc.returncode != 0:
                err = proc.stderr.decode("utf-8", "ignore")
                raise RuntimeError(f"piper failed (code {proc.returncode}): {err}")

            with open(tmp_path, "rb") as f:
                return f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
