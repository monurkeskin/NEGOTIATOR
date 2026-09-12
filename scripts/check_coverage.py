"""Enforce branch coverage for the actual domain, policy and lifecycle modules."""

import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
groups = {
    "domain": ("/domain/",),
    "policies and model adapter": ("/strategies/", "/models/"),
    "session lifecycle": (
        "/events/",
        "/application/session.py",
        "/application/clock.py",
        "/application/runner.py",
    ),
}
failed = False
for name, paths in groups.items():
    files = [v for k, v in report["files"].items() if any(p in k.replace("\\", "/") for p in paths)]
    total = sum(f["summary"]["num_branches"] for f in files)
    covered = sum(f["summary"]["covered_branches"] for f in files)
    fraction = covered / total if total else 0
    print(f"{name}: {covered}/{total} branches = {fraction:.1%}")
    failed |= fraction < 0.90
raise SystemExit(int(failed))
