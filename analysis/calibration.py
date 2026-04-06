from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping


def percentile_calibrate(scores: Iterable[float]) -> list[float]:
    values = list(scores)
    if not values:
        return []
    ordered = sorted((v, i) for i, v in enumerate(values))
    calibrated = [0.0] * len(values)
    n = len(values) - 1 if len(values) > 1 else 1
    idx = 0
    while idx < len(ordered):
        j = idx
        while j < len(ordered) and ordered[j][0] == ordered[idx][0]:
            j += 1
        percentile = (idx + j - 1) / (2 * n) if n else 0.0
        for k in range(idx, j):
            calibrated[ordered[k][1]] = round(percentile, 3)
        idx = j
    return calibrated


CONFIG_PATH = Path("config") / "calibrated_thresholds.json"


@dataclass(frozen=True)
class CalibrationThresholds:
    urgency: Mapping[str, float]
    confidence: Mapping[str, float]
    conflict: Mapping[str, float]
    temporal_urgency: Mapping[str, float]
    phase: Mapping[str, float]


class Calibrator:
    def __init__(self, thresholds: CalibrationThresholds) -> None:
        self._thresholds = thresholds

    def map_urgency(self, score: float) -> str:
        return _bucket(
            score,
            self._thresholds.urgency,
            levels=("low", "medium", "high", "critical"),
        )

    def map_confidence(self, score: float) -> str:
        return _bucket(
            score,
            self._thresholds.confidence,
            levels=("low", "medium", "high"),
        )

    def urgency_signal_min(self) -> float:
        return float(
            self._thresholds.urgency.get(
                "signal_min",
                self._thresholds.urgency.get("medium_min", 0.0),
            )
        )

    def urgency_boost_min(self) -> float:
        return float(
            self._thresholds.urgency.get(
                "boost_min",
                self._thresholds.urgency.get("medium_min", 0.0),
            )
        )

    def urgency_boost_high(self) -> float:
        return float(
            self._thresholds.urgency.get(
                "boost_high",
                self._thresholds.urgency.get("high_min", 0.0),
            )
        )

    def conflict_threshold(self) -> float:
        return float(self._thresholds.conflict.get("alternation_min", 0.0))

    def temporal_signal_min(self) -> float:
        return float(self._thresholds.temporal_urgency.get("signal_min", 0.0))

    def temporal_quiet_max(self) -> float:
        return float(self._thresholds.temporal_urgency.get("quiet_max", 0.0))

    def temporal_hotfix_min(self) -> float:
        return float(self._thresholds.temporal_urgency.get("hotfix_min", 0.0))

    def temporal_hotfix_high(self) -> float:
        return float(self._thresholds.temporal_urgency.get("hotfix_high", 0.0))

    def temporal_initial_max(self) -> float:
        return float(self._thresholds.temporal_urgency.get("initial_max", 0.0))

    def phase_dominance_min(self) -> float:
        return float(self._thresholds.phase.get("dominant_ratio_min", 0.0))


def _bucket(score: float, thresholds: Mapping[str, float], levels: tuple[str, ...]) -> str:
    if "critical_min" in thresholds and score >= float(thresholds["critical_min"]):
        return "critical"
    if "high_min" in thresholds and score >= float(thresholds["high_min"]):
        return "high"
    if "medium_min" in thresholds and score >= float(thresholds["medium_min"]):
        return "medium"
    return levels[0]


def _load_threshold_section(
    payload: Mapping[str, object], key: str
) -> Mapping[str, float]:
    section = payload.get(key)
    if not isinstance(section, Mapping):
        raise ValueError(f"Calibration config missing '{key}' section.")
    parsed: dict[str, float] = {}
    for name, value in section.items():
        try:
            parsed[name] = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Calibration config '{key}.{name}' must be numeric."
            ) from exc
    return parsed


def load_thresholds(path: str | Path = CONFIG_PATH) -> CalibrationThresholds:
    config_path = Path(path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Calibration config must be an object.")
    return CalibrationThresholds(
        urgency=_load_threshold_section(payload, "urgency"),
        confidence=_load_threshold_section(payload, "confidence"),
        conflict=_load_threshold_section(payload, "conflict"),
        temporal_urgency=_load_threshold_section(payload, "temporal_urgency"),
        phase=_load_threshold_section(payload, "phase"),
    )


@lru_cache(maxsize=1)
def load_calibrator(path: str | Path = CONFIG_PATH) -> Calibrator:
    return Calibrator(load_thresholds(path))
