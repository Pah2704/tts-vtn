# backend/tests/test_xtts_limits.py
import pytest
from backend.modules.tts_manager import TTSManager, SynthesisConfig, pick_device

def _cfg():
    # Khớp với SynthesisConfig của bạn
    return SynthesisConfig(voice_id="vi_female_01", speed=1.0, emotions=None)

def test_xtts_limit_allows_2000():
    mgr = TTSManager(engine="xtts")
    audio = mgr.synthesize("a" * 2000, _cfg())
    assert isinstance(audio, (bytes, bytearray)) and len(audio) > 0

def test_xtts_limit_raises_above_2000():
    mgr = TTSManager(engine="xtts")
    with pytest.raises(ValueError):
        mgr.synthesize("a" * 2001, _cfg())

def test_pick_device_returns_expected_str():
    dev = pick_device()
    assert dev in ("cpu", "cuda")
