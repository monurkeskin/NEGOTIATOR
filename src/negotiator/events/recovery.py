"""Recover a verified journal prefix into a new directory; original bytes stay intact."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .journal import Journal, JournalError


def recover_copy(source: Path, destination: Path) -> Path:
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError("Recovery requires a new directory; existing records are preserved.")
    raw = source.read_bytes()
    destination.mkdir(parents=True)
    target = destination / "events.jsonl"
    target.write_bytes(b"")
    accepted = 0
    failure = None
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            failure = "truncated_record"
            break
        with target.open("ab") as stream:
            stream.write(line)
        try:
            Journal(target).read()
        except JournalError as exc:
            failure = str(exc)
            with target.open("r+b") as stream:
                stream.truncate(accepted)
            break
        accepted += len(line)
    if not accepted:
        raise JournalError("No valid prefix could be recovered. Original source is unchanged.")
    shutil.copyfile(source.with_name("manifest.json"), destination / "manifest.json")
    from negotiator.application.session import Session

    # A copied active session becomes interrupted; it is never resumed as a human trial.
    Session.open(target)
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "verified_prefix_bytes": accepted,
        "discarded_suffix_bytes": len(raw) - accepted,
        "failure": failure,
        "original_preserved": True,
    }
    (destination / "recovery.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return destination
