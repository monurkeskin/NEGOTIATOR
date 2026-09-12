"""Distribution-facing contracts use the documented files and real calculation paths."""

import json
from pathlib import Path

import pytest

from negotiator.metadata import metadata_files, write_metadata
from negotiator.reproduction import run_reproduction

ROOT = Path(__file__).resolve().parents[1]


def test_paper_and_software_dois_remain_distinct_in_all_citation_outputs():
    record = json.loads((ROOT / "citation-metadata.json").read_text(encoding="utf-8"))
    record["software"]["doi"] = "10.5072/zenodo.123456"
    generated = metadata_files(record)
    cff = json.loads(generated["CITATION.cff"])
    assert cff["preferred-citation"]["doi"] == record["paper"]["doi"]
    assert cff["doi"] == record["software"]["doi"]
    assert (
        json.loads(generated["codemeta.json"])["identifier"]
        == "https://doi.org/10.5072/zenodo.123456"
    )
    assert json.loads(generated[".zenodo.json"])["doi"] == record["software"]["doi"]
    assert "@software{" in generated["reference.bib"]
    assert record["software"]["doi"] in generated["reference.bib"]
    assert record["paper"]["doi"] in generated["reference.bib"]


def test_citation_outputs_match_the_common_record_and_framework_title():
    record = json.loads((ROOT / "citation-metadata.json").read_text(encoding="utf-8"))
    write_metadata(ROOT, record, check=True)
    assert record["paper"]["title"] in (ROOT / "README.md").read_text(encoding="utf-8")
    assert (
        json.loads((ROOT / "CITATION.cff").read_text(encoding="utf-8"))["preferred-citation"]["doi"]
        == "10.24963/ijcai.2024/1012"
    )


def test_paper_map_names_real_source_labels_and_existing_tests():
    mapping = json.loads((ROOT / "paper-map.json").read_text(encoding="utf-8"))
    assert len({r["id"] for r in mapping["requirements"]}) == len(mapping["requirements"])
    for item in mapping["requirements"]:
        assert item["sources"]
        for source in item["sources"]:
            assert source["label"] and source["line"] > 0 and len(source["sha256"]) == 64
        for test in item["tests"]:
            assert (ROOT / test["path"]).is_file()


@pytest.mark.parametrize("name", ["method.json", "paired.json"])
def test_readme_reproduction_commands_compute_and_export(name, tmp_path):
    result = run_reproduction(ROOT / "examples/reproduction" / name, tmp_path / "output")
    assert result["status"] == "verified"
    crate = json.loads((tmp_path / "output/ro-crate-metadata.json").read_text(encoding="utf-8"))
    root = next(x for x in crate["@graph"] if x["@id"] == "./")
    assert root["datePublished"] and root["license"] and root["description"]
