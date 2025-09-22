from backend.modules.audio_pipeline import normalize_to_lufs, peak_limit
from backend.modules.quality_control import measure_metrics

def test_normalize_to_target_lufs(sine_wav):
    out = normalize_to_lufs(sine_wav, -16.0)
    m = measure_metrics(out)
    # Cho phép sai số nhỏ ±1 LU
    assert -17.0 <= m["lufsIntegrated"] <= -15.0

def test_peak_limit_ceiling(sine_wav):
    out = peak_limit(sine_wav, -1.0)
    m = measure_metrics(out)
    # True peak (xấp xỉ) không vượt quá -1 dBFS nhiều hơn 0.2 dB
    assert m["truePeakDb"] <= -0.8
