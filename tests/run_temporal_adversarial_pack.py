from __future__ import annotations

import json
from pathlib import Path

from tests.golden import analyze_fixture, compare_golden_view, load_expected_json, to_golden_view


FIXTURES = [
    "temporal_busy_harmless_burst",
    "temporal_high_impact_calm_work",
    "temporal_silent_firefight",
    "temporal_alternation_noise",
    "temporal_real_conflict_alternation",
    "temporal_micro_burst_fragmentation",
    "temporal_sparse_critical_work",
    "temporal_fake_diversity_attack",
    "temporal_proactive_disguised_reactive",
    "temporal_spike_mixed_impact",
]


def main() -> int:
    failures: list[tuple[str, str, dict, dict]] = []

    for name in FIXTURES:
        actual = to_golden_view(analyze_fixture(name))
        expected = load_expected_json(name)
        try:
            compare_golden_view(actual, expected)
        except AssertionError as exc:
            failures.append((name, str(exc) or "assertion failed", actual, expected))

    if not failures:
        print("Temporal adversarial pack: all scenarios passed")
        return 0

    print(f"Temporal adversarial pack: {len(failures)} scenario(s) failed")
    for name, message, actual, expected in failures:
        print("=" * 80)
        print(name)
        print(f"failure: {message}")
        print("expected:")
        print(json.dumps(expected, indent=2))
        print("actual:")
        print(json.dumps(actual, indent=2))

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
