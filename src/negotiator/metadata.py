"""Generate consistent citation and archive metadata from one maintained record."""

import json
from pathlib import Path
from typing import Any

from negotiator.citations import bibtex_entry


def metadata_files(record: dict[str, Any]) -> dict[str, str]:
    software, paper = record["software"], record["paper"]
    if not paper.get("title") or not paper.get("authors") or not paper.get("year"):
        raise ValueError("Preferred paper citation needs title, authors and publication year.")
    if not software.get("version") or not software.get("repository-code"):
        raise ValueError("Software metadata needs a version and repository URL.")
    paper_url = "https://doi.org/" + paper["doi"] if paper.get("doi") else paper["url"]
    cff = {**software, "preferred-citation": paper}
    codemeta = {
        "@context": "https://doi.org/10.5063/schema/codemeta-2.0",
        "@type": "SoftwareSourceCode",
        "name": software["title"],
        "version": software["version"],
        "codeRepository": software["repository-code"],
        "datePublished": software["date-released"],
        "license": "https://spdx.org/licenses/" + software["license"] + ".html",
        "author": [
            {
                "@type": "Person",
                "givenName": a.get("given-names", ""),
                "familyName": a["family-names"],
            }
            for a in software["authors"]
        ],
        "citation": {"@type": "ScholarlyArticle", "name": paper["title"], "identifier": paper_url},
        "programmingLanguage": ["Python"],
        "runtimePlatform": "Python >=3.11",
    }
    zenodo = {
        "title": software["title"],
        "version": software["version"],
        "upload_type": "software",
        "description": "Maintained research software for "
        + paper["title"]
        + ". Reproducibility scope and source provenance are documented in the repository.",
        "creators": [
            {"name": a["family-names"] + ", " + a.get("given-names", "")}
            for a in software["authors"]
        ],
        "license": software["license"],
        "related_identifiers": [
            {
                "identifier": paper.get("doi") or paper_url,
                "relation": "isSupplementTo",
                "scheme": "doi" if paper.get("doi") else "url",
            }
        ],
    }
    if software.get("doi"):
        codemeta["identifier"] = "https://doi.org/" + software["doi"]
        zenodo["doi"] = software["doi"]
    software_citation = {
        **software,
        "year": int(software["date-released"][:4]),
        "url": software["repository-code"],
    }

    def encoded(value: Any) -> str:
        return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"

    # JSON is a YAML 1.2 subset and avoids ambiguous dates or folded paper titles in CFF.
    return {
        "CITATION.cff": encoded(cff),
        "codemeta.json": encoded(codemeta),
        ".zenodo.json": encoded(zenodo),
        "reference.bib": bibtex_entry(record["bibtex_key"], paper)
        + "\n"
        + bibtex_entry(record["bibtex_key"] + "Software", software_citation, software=True),
    }


def write_metadata(root: Path, record: dict[str, Any], *, check: bool = False) -> None:
    for name, contents in metadata_files(record).items():
        path = root / name
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != contents:
                raise ValueError("Generated citation metadata differs: " + str(path))
        else:
            path.write_text(contents, encoding="utf-8")
