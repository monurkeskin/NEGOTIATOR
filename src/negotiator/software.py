"""Content and dependency identities of the installed implementation."""

import hashlib
import json
import platform
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path
from typing import Any

from negotiator import __version__


def package_content_hash(root: Path, provenance: Path | None = None) -> str:
    paths = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in (".py", ".pyi", ".json", ".xml", ".js", ".css", ".html")
    }
    if "provenance.json" not in paths and provenance is not None:
        paths["provenance.json"] = provenance
    digest = hashlib.sha256()
    for name, path in sorted(paths.items()):
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


@lru_cache(maxsize=1)
def _content_hash() -> str:
    root = Path(__file__).parent
    return package_content_hash(
        root,
        root.parents[1] / "provenance.json" if not (root / "provenance.json").is_file() else None,
    )


@lru_cache(maxsize=1)
def _dependencies() -> tuple[tuple[str, str], ...]:
    return tuple(
        (name, version(name))
        for name in (
            "defusedxml",
            "fastapi",
            "uvicorn",
            "matplotlib",
            "openpyxl",
            "numpy",
            "pydantic",
        )
    )


def runtime_identity() -> dict[str, Any]:
    record = json.loads(
        (Path(__file__).parent / "data/citations.json").read_text(encoding="utf-8")
    )["records"]["NEGOTIATOR"]["software"]
    return {
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "package_content_sha256": _content_hash(),
        "dependencies": dict(_dependencies()),
        **(
            {"doi": record["doi"]} if record.get("doi") and record["version"] == __version__ else {}
        ),
    }
