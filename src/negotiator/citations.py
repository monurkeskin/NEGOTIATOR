"""Citations follow verified run records and executed method diagnostics."""

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from negotiator.events.journal import Journal, digest
from negotiator.events.projection import replay

METHOD_PAPERS = {
    "tsbt": "jennifer-negotiation-2021",
    "babt": "jennifer-negotiation-2022",
    "hybrid": "solver-agent-2021",
    "solver-2021": "solver-agent-2021",
    "solver-2025": "emotion-aware-negotiation-2025",
}


def registry() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        files("negotiator").joinpath("data/citations.json").read_text(encoding="utf-8")
    )
    records: dict[str, Any] = data["records"]
    return records


def run_citations(root: Path) -> dict[str, Any]:
    root = Path(root)
    records = registry()
    selected = set()
    versions = {}
    found = False
    for path in sorted(root.rglob("manifest.json")):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if "configuration_sha256" not in metadata:
            continue
        if digest(metadata["configuration"]) != metadata["configuration_sha256"]:
            raise ValueError("Run manifest configuration hash mismatch.")
        events = Journal(path.with_name("events.jsonl")).read()
        if not events:
            continue
        if events[0].kind == "study.changed":
            continue
        if events[0].kind != "session.started":
            continue
        replay(events)
        if digest(events[0].payload) != metadata["configuration_sha256"]:
            raise ValueError("Run start event hash differs from manifest.")
        found = True
        selected.add("NEGOTIATOR")
        selected.update(events[0].payload["config"].get("citation_ids", []))
        software = events[0].payload.get("software")
        if software is not None:
            versions[digest(software)] = software
        for event in events:
            diagnostics = event.payload.get("diagnostics") or {}
            if diagnostics.get("strategy") in METHOD_PAPERS:
                selected.add(METHOD_PAPERS[diagnostics["strategy"]])
            if diagnostics.get("model_observations", 0) > 0:
                selected.add("CBOM")
    if not found:
        raise ValueError("No verified session records found in this run directory.")
    unknown = selected - records.keys()
    if unknown:
        raise ValueError("No citation metadata registered for: " + ", ".join(sorted(unknown)))
    return {
        "papers": [
            {"id": key, **records[key]["paper"], "bibtex_key": records[key]["bibtex_key"]}
            for key in sorted(selected)
        ],
        "software_versions": list(versions.values()),
    }


def bibtex_entry(key: str, citation: dict[str, Any], *, software: bool = False) -> str:
    kind = (
        "software"
        if software
        else "article"
        if citation.get("type") == "article"
        else "inproceedings"
    )
    author = " and ".join(
        person["family-names"] + ", " + person["given-names"] for person in citation["authors"]
    )
    fields = {"title": citation["title"], "author": author}
    for name in ("year", "doi", "url", "version", "note", "journal", "volume"):
        if name in citation:
            fields[name] = str(citation[name])
    if citation.get("conference"):
        fields["booktitle"] = citation["conference"]["name"]
    elif citation.get("collection-title"):
        fields["booktitle"] = citation["collection-title"]

    def clean(value: str) -> str:
        return value.replace("\\", r"\textbackslash{}").replace("%", r"\%").replace("&", r"\&")

    return (
        "@"
        + kind
        + "{"
        + key
        + ",\n"
        + ",\n".join("  " + name + " = {" + clean(value) + "}" for name, value in fields.items())
        + "\n}\n"
    )


def to_bibtex(citations: dict[str, Any]) -> str:
    entries = [bibtex_entry(record["bibtex_key"], record) for record in citations["papers"]]
    for index, software in enumerate(citations["software_versions"]):
        entries.append(
            bibtex_entry(
                f"negotiatorSoftware{index + 1}",
                {
                    "title": "NEGOTIATOR research software",
                    "authors": registry()["NEGOTIATOR"]["software"]["authors"],
                    "version": software["version"],
                    **({"doi": software["doi"]} if software.get("doi") else {}),
                    "url": "https://github.com/monurkeskin/NEGOTIATOR",
                    "note": "Package content SHA256: " + software["package_content_sha256"],
                },
                software=True,
            )
        )
    return "\n".join(entries)
