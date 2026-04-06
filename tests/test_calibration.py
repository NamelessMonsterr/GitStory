from __future__ import annotations

from analysis.calibration import load_calibrator, percentile_calibrate


def test_percentile_calibrate_monotonic() -> None:
    values = [0.1, 0.2, 0.2, 0.5, 0.9]
    calibrated = percentile_calibrate(values)
    assert len(calibrated) == len(values)
    assert all(0.0 <= v <= 1.0 for v in calibrated)
    assert calibrated[0] <= calibrated[1] <= calibrated[3] <= calibrated[4]


def test_percentile_calibrate_empty() -> None:
    assert percentile_calibrate([]) == []


def test_calibrator_maps_using_config() -> None:
    calibrator = load_calibrator()
    assert calibrator.map_urgency(0.1) == "low"
    assert calibrator.map_urgency(0.6) in {"medium", "high"}
    assert calibrator.map_confidence(0.8) == "high"
