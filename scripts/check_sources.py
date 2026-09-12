"""Check the selected verbatim upstream components and their distributed manifest."""

import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
count = 0
for component in manifest["components"]:
    for item in component.get("selected_files", []):
        if "destination" not in item:
            continue
        path = root / item["destination"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise SystemExit("Source hash differs: " + item["destination"])
        count += 1
print(f"{count} selected source/asset hashes match.")
