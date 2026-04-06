from __future__ import annotations

from typing import Iterable


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
