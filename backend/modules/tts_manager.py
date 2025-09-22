"""
TTS Manager — Piper adapter (CLI).
- Đọc env PIPER_BIN, PIPER_MODEL_PATH, PIPER_CONFIG_PATH.
- Map speed 0.5–2.0 -> --length_scale = 1/speed.
"""
from dataclasses import dataclass
from typing import Optional, List, Literal
import os, shutil, subprocess, tempfile
from ..core.config import settings

EmotionTag = Literal["happy", "sad", "excited", "calm", "serious", "whisper"]

@dataclass(frozen=True)
class SynthesisConfig:
    voice_id: str
    speed: float = 1.0
    emotions: Optional[List[EmotionTag]] = None  # Piper CLI chưa dùng; để future

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
            raise RuntimeError("Piper binary not found. Ensure PIPER_BIN in PATH or set env PIPER_BIN.")
        if not self.model_path or not os.path.exists(self.model_path):
            raise RuntimeError("Missing PIPER_MODEL_PATH or file not found.")
        # config có thể thiếu với 1 số model, nhưng khuyến nghị có:
        if self.config_path and (not os.path.exists(self.config_path)):
            raise RuntimeError("PIPER_CONFIG_PATH set but file not found.")

    def synthesize(self, text: str, cfg: SynthesisConfig) -> bytes:
        """
        PRE: text != "" (trim), 0.5 <= cfg.speed <= 2.0
        POST: trả WAV (16-bit/float tuỳ model) dạng bytes.
        ERROR: ValueError input, RuntimeError khi Piper CLI lỗi.
        """
        txt = (text or "").strip()
        if not txt:
            raise ValueError("text is empty")
        if not (0.5 <= float(cfg.speed) <= 2.0):
            raise ValueError("speed out of range [0.5,2.0]")

        length_scale = 1.0 / float(cfg.speed)

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            cmd = [self.piper_bin, "--model", self.model_path, "--output_file", tmp_path,
                   "--length-scale", f"{length_scale:.3f}"]
            if self.config_path:
                cmd += ["--config", self.config_path]

            # Piper đọc text từ stdin
            proc = subprocess.run(
                cmd, input=txt.encode("utf-8"),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
            , timeout=settings.PIPER_TIMEOUT_SEC)
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
