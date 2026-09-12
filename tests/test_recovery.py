import hashlib
import json

import pytest

from negotiator.events.journal import Journal
from negotiator.events.projection import replay
from negotiator.events.recovery import recover_copy
from negotiator.examples import run_demo


def test_recovery_preserves_damaged_source_and_reports_lost_suffix(tmp_path):
    session = run_demo(tmp_path / "original")
    source = session.journal.path
    clean = source.read_bytes()
    damaged = clean + b'{"unfinished":'
    source.write_bytes(damaged)
    recovered = recover_copy(source, tmp_path / "recovered")
    assert source.read_bytes() == damaged
    assert replay(Journal(recovered / "events.jsonl").read()).outcome["reason"] == "agreement"
    receipt = json.loads((recovered / "recovery.json").read_text(encoding="utf-8"))
    assert receipt["discarded_suffix_bytes"] == len(damaged) - len(clean)
    assert receipt["source_sha256"] == hashlib.sha256(damaged).hexdigest()
    with pytest.raises(ValueError):
        recover_copy(source, recovered)
