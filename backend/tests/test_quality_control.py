from backend.modules.quality_control import measure_metrics

def test_measure_metrics_keys_and_ranges(sine_wav):
    m = measure_metrics(sine_wav)
    # Keys tồn tại
    assert {"lufsIntegrated", "truePeakDb", "durationSec"} <= set(m.keys())
    # Giá trị hợp lý
    assert m["durationSec"] > 0.9 and m["durationSec"] < 1.1
    assert m["truePeakDb"] < 0.0  # peak luôn âm dBFS
