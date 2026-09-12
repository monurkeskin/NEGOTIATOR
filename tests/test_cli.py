import json
import subprocess
import sys


def run(*args):
    return subprocess.run(
        [sys.executable, "-m", "negotiator", *map(str, args)],
        check=True,
        text=True,
        capture_output=True,
    )


def test_independent_offline_demo_and_replay(tmp_path):
    result = json.loads(run("demo", "--output", tmp_path).stdout)
    assert result["synthetic"] is True
    assert result["outcome"]["reason"] == "agreement"
    replayed = json.loads(run("replay", result["journal"]).stdout)
    assert replayed["outcome"] == result["outcome"]
    assert len(replayed["offers"]) == 2


def test_doctor_does_not_require_devices_or_other_source_repositories():
    result = json.loads(run("doctor").stdout)
    assert result["offline_demo_ready"]
    assert result["python"]
    assert result["hardware_validation"] == "not_performed"
