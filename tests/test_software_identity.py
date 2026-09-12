from negotiator.software import runtime_identity


def test_callers_cannot_change_later_run_identity():
    first = runtime_identity()
    actual = first["package_content_sha256"]
    first["package_content_sha256"] = "fake"
    assert runtime_identity()["package_content_sha256"] == actual


def test_source_and_wheel_have_the_same_logical_package_hash(tmp_path):
    from negotiator.software import package_content_hash

    source = tmp_path / "source"
    wheel = tmp_path / "wheel"
    source.mkdir()
    wheel.mkdir()
    for root in (source, wheel):
        (root / "module.py").write_text("x=1\n", encoding="utf-8")
    provenance = tmp_path / "provenance.json"
    provenance.write_text('{"source":"approved"}', encoding="utf-8")
    (wheel / "provenance.json").write_bytes(provenance.read_bytes())
    assert package_content_hash(source, provenance) == package_content_hash(wheel)
    (wheel / "module.py").write_text("x=2\n", encoding="utf-8")
    assert package_content_hash(source, provenance) != package_content_hash(wheel)
