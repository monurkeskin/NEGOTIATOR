import sys
import time

import pytest

from negotiator.adapters.process import BridgeConfig, BridgeError, ProcessBridge
from negotiator.examples import run_demo
from negotiator.interaction.presentation import Presenter


def config(**changes):
    return BridgeConfig(
        command=[sys.executable, "-m", "negotiator.bridges.synthetic"],
        family="synthetic",
        expected_runtime="synthetic-1",
        **changes,
    )


def test_bridge_is_lazy_bounded_and_correlates_every_response():
    bridge = ProcessBridge(config())
    assert bridge.process is None
    result = bridge.connect()
    assert result["capabilities"] == ["speech", "gesture", "face", "transcript", "affect"]
    result = bridge.request("s1", "e1", "present", {"text": "Synthetic offer"})
    assert result["delivered"] is True
    bridge.close()
    bridge.close()
    with pytest.raises(BridgeError):
        bridge.request("s1", "e2", "present", {})


def test_runtime_mismatch_and_timeout_fail_without_fallback():
    bad = config().model_copy(update={"expected_runtime": "different"})
    with pytest.raises(BridgeError, match="runtime"):
        ProcessBridge(bad).connect()
    bridge = ProcessBridge(config())
    bridge.connect()
    # Isolate request timeout from interpreter startup on busy CI hosts.
    bridge.config = bridge.config.model_copy(update={"timeout_seconds": 0.05})
    start = time.monotonic()
    with pytest.raises(BridgeError, match="timed out"):
        bridge.request("s1", "e1", "wait", {})
    assert time.monotonic() - start < 2
    assert bridge.process is None


def test_protocol_mismatch_closes_the_bridge():
    bridge = ProcessBridge(config())
    bridge.connect()
    with pytest.raises(BridgeError, match="identity"):
        bridge.request("s1", "e1", "wrong_identity", {})
    assert bridge.process is None


def test_presentation_delivery_does_not_create_another_bid(tmp_path):
    session = run_demo(tmp_path)
    original = session.state.offers
    bridge = ProcessBridge(config())
    bridge.connect()
    presenter = Presenter(session, bridge)
    event = next(
        e
        for e in session.journal.read()
        if e.kind == "offer.committed" and e.payload["actor"] == "agent"
    )
    presenter.deliver(event)
    presenter.deliver(event)
    assert session.state.offers == original
    records = session.journal.read()
    assert sum(e.kind == "presentation.delivered" for e in records) == 1
    assert not any(e.kind == "presentation.visible" for e in records)
    bridge.close()


def test_unknown_delivery_is_not_automatically_retried(tmp_path, monkeypatch):
    session = run_demo(tmp_path)
    bridge = ProcessBridge(config())
    bridge.connect()
    presenter = Presenter(session, bridge)
    event = next(e for e in session.journal.read() if e.kind == "session.ended")
    calls = []

    def fail(*args):
        calls.append(args)
        raise BridgeError("disconnected after send")

    monkeypatch.setattr(bridge, "request", fail)
    presenter.deliver(event)
    presenter.deliver(event)
    assert len(calls) == 1
    failed = [e for e in session.journal.read() if e.kind == "presentation.failed"]
    assert failed[0].payload["delivery_status"] == "unknown"
    bridge.close()


def test_gui_device_session_records_delivery_and_closes_at_end(tmp_path):
    from negotiator.application.contracts import StudySpec
    from negotiator.application.studies import StudyStore

    bridge_config = config()
    store = StudyStore(tmp_path, "test", devices={"nao": bridge_config})
    pid = store.create(StudySpec(preference_mode="assigned", output="nao", first_actor="agent"))[
        "plan_id"
    ]
    store.start(pid)
    sid = store.snapshot(pid)["current"]["config"]["session_id"]
    deadline = time.monotonic() + 3
    while store.snapshot(pid)["presentation_pending"] and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not store.snapshot(pid)["presentation_pending"]
    store.terminate(pid, "Synthetic stop", "stop")
    store.shutdown()
    records = store._sessions[sid].journal.read()
    assert sum(e.kind == "presentation.delivered" for e in records) == 2
    assert not store._presenters[sid].thread.is_alive()


def test_facechannel_dimensional_heads_are_not_swapped():
    from negotiator.bridges.facechannel import dimensional_output

    assert dimensional_output([[[0.8]], [[-0.3]]]) == {"arousal": 0.8, "valence": -0.3}
    with pytest.raises(ValueError):
        dimensional_output([float("nan"), 0.2])


def test_assets_require_provenance_and_do_not_accept_changed_model_bytes(tmp_path):
    import hashlib
    import json

    from negotiator.bridges.assets import verify_assets

    model = tmp_path / "model.bin"
    model.write_bytes(b"synthetic model")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source_url": "https://example.org/synthetic",
                "license": "CC0-1.0",
                "files": {"model.bin": hashlib.sha256(model.read_bytes()).hexdigest()},
            }
        ),
        encoding="utf-8",
    )
    assert verify_assets(manifest)[0] == tmp_path
    model.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_assets(manifest)


def test_delivery_latency_uses_monotonic_time_even_after_session_end(tmp_path, monkeypatch):
    session = run_demo(tmp_path)
    bridge = ProcessBridge(config())
    bridge.connect()
    times = iter([100.0, 100.25])
    monkeypatch.setattr("negotiator.interaction.presentation.monotonic", lambda: next(times))
    Presenter(session, bridge).deliver(
        next(e for e in session.journal.read() if e.kind == "session.ended")
    )
    receipt = next(e.payload for e in session.journal.read() if e.kind == "presentation.delivered")
    assert receipt["request_elapsed_seconds"] == 0.25
    bridge.close()
