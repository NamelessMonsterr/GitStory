from __future__ import annotations

import json
from pathlib import Path

from evaluation.evaluator import load_labeled


def test_label_schema_and_sample_load() -> None:
    schema_path = Path("data") / "labeled" / "label_schema.json"
    sample_path = Path("data") / "labeled" / "sample_labeled_data.json"

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["type"] == "array"
    assert "items" in schema

    records = load_labeled(sample_path)
    assert len(records) >= 3
