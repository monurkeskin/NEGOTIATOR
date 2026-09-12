import json

import pytest

from negotiator.application.runner import SessionRunner
from negotiator.application.session import Session, SessionConfig
from negotiator.domain.actions import End
from negotiator.examples import builtin_domain, example_profiles


def test_citations_follow_executed_components_and_record_software(tmp_path):
    from negotiator.citations import run_citations

    human, own = example_profiles(builtin_domain("fruits"))
    session = Session.create(
        tmp_path,
        SessionConfig("example", "P1", "S1", strategy="tsbt", first_actor="agent"),
        human,
        own,
    )
    SessionRunner(session).respond()
    session.submit(End("human", "withdrawal"), "end")
    citations = run_citations(tmp_path)
    ids = {record["id"] for record in citations["papers"]}
    assert "NEGOTIATOR" in ids
    assert "jennifer-negotiation-2021" in ids
    assert "solver-agent-2021" not in ids
    assert "emotion-aware-negotiation-2025" not in ids
    assert citations["software_versions"][0]["version"]
    assert citations["software_versions"][0]["package_content_sha256"]


def test_unexecuted_strategy_does_not_add_a_method_citation(tmp_path):
    from negotiator.citations import run_citations

    human, own = example_profiles(builtin_domain("fruits"))
    session = Session.create(
        tmp_path, SessionConfig("example", "P1", "S1", strategy="solver-2025"), human, own
    )
    session.submit(End("human", "withdrawal"), "end")
    citations = run_citations(tmp_path)
    assert [record["id"] for record in citations["papers"]] == ["NEGOTIATOR"]


def test_cite_cli_and_missing_run(tmp_path, capsys):
    from negotiator.citations import run_citations
    from negotiator.cli import main

    human, own = example_profiles(builtin_domain("fruits"))
    session = Session.create(tmp_path, SessionConfig("example", "P1", "S1"), human, own)
    session.submit(End("human", "withdrawal"), "end")
    assert main(["cite", str(tmp_path), "--format", "bibtex"]) == 0
    result = capsys.readouterr().out
    assert "@inproceedings{" in result
    assert "10.24963/ijcai.2024/1012" in result
    assert "@software{" in result
    with pytest.raises(ValueError, match="No verified"):
        run_citations(tmp_path / "absent")


def test_changed_manifest_is_not_used_as_citation_evidence(tmp_path):
    from negotiator.citations import run_citations

    human, own = example_profiles(builtin_domain("fruits"))
    Session.create(tmp_path, SessionConfig("example", "P1", "S1"), human, own)
    path = next(tmp_path.rglob("manifest.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["configuration"]["config"]["strategy"] = "solver-2025"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        run_citations(tmp_path)


def test_an_unstarted_study_does_not_add_unused_paper_citations(tmp_path):
    from negotiator.application.contracts import StudySpec
    from negotiator.application.studies import StudyStore
    from negotiator.citations import run_citations

    store = StudyStore(tmp_path)
    store.create(StudySpec(citation_ids=["unregistered-unused-paper"]))
    pid = store.create(StudySpec(preference_mode="assigned", citation_ids=["solver-agent-2021"]))[
        "plan_id"
    ]
    store.start(pid)
    assert "solver-agent-2021" in {p["id"] for p in run_citations(tmp_path)["papers"]}
    store.shutdown()


def test_software_doi_is_taken_from_the_recorded_run_identity():
    from negotiator.citations import to_bibtex

    identity = {
        "version": "2.0.0",
        "package_content_sha256": "a" * 64,
        "doi": "10.5072/zenodo.123456",
    }
    assert identity["doi"] in to_bibtex({"papers": [], "software_versions": [identity]})
    identity.pop("doi")
    assert "doi =" not in to_bibtex({"papers": [], "software_versions": [identity]})


@pytest.mark.parametrize("output_format", ["json", "bibtex"])
def test_citation_pipe_is_utf8_even_with_a_legacy_windows_encoding(tmp_path, output_format):
    import os
    import subprocess
    import sys

    human, own = example_profiles(builtin_domain("fruits"))
    session = Session.create(tmp_path, SessionConfig("example", "P1", "S1"), human, own)
    session.submit(End("human", "withdrawal"), "end")
    result = subprocess.run(
        [sys.executable, "-m", "negotiator", "cite", str(tmp_path), "--format", output_format],
        env={**os.environ, "PYTHONIOENCODING": "cp1252:strict"},
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert "Aydoğan" in result.stdout.decode("utf-8")
