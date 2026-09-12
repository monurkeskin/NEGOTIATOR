"""Read-only, explicitly mapped legacy observations; never invent session provenance."""

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from negotiator.domain.preferences import finite_number


def import_legacy(
    source: Path, mapping: dict[str, str], output: Path, *, arousal_overwritten: bool = False
) -> Path:
    if output.exists():
        raise ValueError("Choose a new output file to preserve previous imports.")
    allowed = {
        "session_id",
        "participant_id",
        "actor",
        "bid",
        "elapsed_seconds",
        "human_utility",
        "agent_utility",
        "valence",
        "arousal",
    }
    if not mapping or set(mapping) - allowed:
        raise ValueError("Supply an explicit supported field-to-column mapping.")
    rows = []
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if set(mapping.values()) - set(reader.fieldnames or []):
            raise ValueError("A mapped column is absent from the source CSV.")
        for number, row in enumerate(reader, 2):
            values: dict[str, Any] = {}
            missing = {}
            for field in sorted(allowed):
                value = row.get(mapping.get(field, ""), "").strip()
                if field == "arousal" and arousal_overwritten:
                    values[field], missing[field] = None, "legacy_arousal_overwritten_unrecoverable"
                elif not value:
                    values[field], missing[field] = None, "not_recorded"
                elif field in {
                    "elapsed_seconds",
                    "human_utility",
                    "agent_utility",
                    "valence",
                    "arousal",
                }:
                    values[field] = finite_number(float(value), field)
                elif field == "bid":
                    values[field] = json.loads(value)
                else:
                    values[field] = value
            rows.append(
                {"source_line": number, "reported_values": values, "missing_reasons": missing}
            )
    result = {
        "schema_version": 1,
        "format": "legacy-observations-v1",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "mapping": mapping,
        "arousal_overwritten": arousal_overwritten,
        "rows": rows,
        "limitations": [
            "Reported utilities are unverified without the original profiles.",
            "No strategy, deadline, seed or experimental identity is inferred.",
            "This import is separate from canonical new-session journals.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return output
