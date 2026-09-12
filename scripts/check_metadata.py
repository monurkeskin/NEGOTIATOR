"""Check generated citation formats against their single source record."""

import json
from pathlib import Path

from negotiator.metadata import write_metadata

root = Path(__file__).resolve().parents[1]
record = json.loads((root / "citation-metadata.json").read_text(encoding="utf-8"))
write_metadata(root, record, check=True)
print("Citation, BibTeX, CodeMeta and archive metadata agree.")
