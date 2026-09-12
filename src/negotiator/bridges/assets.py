"""Local model assets must have declared provenance and verified byte hashes."""

import hashlib
import json
from pathlib import Path


def verify_assets(path):
    path = Path(path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not manifest.get("source_url") or not manifest.get("license") or not manifest.get("files"):
        raise ValueError("Asset manifest needs source_url, license and a nonempty files hash map.")
    root = path.parent.resolve()
    for name, expected in manifest["files"].items():
        target = (root / name).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError("Missing asset or path outside the asset directory: " + name)
        with target.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise ValueError("Asset hash mismatch: " + name)
    return root, manifest
