"""Check an installed wheel, including its real HTTP UI, away from source checkout."""

import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from importlib.resources import files
from pathlib import Path

import negotiator

package = files("negotiator")
checkout = Path(__file__).resolve().parents[1]
assert not Path(negotiator.__file__).is_relative_to(checkout / "src"), (
    "Use the fresh wheel environment."
)
manifest = json.loads(package.joinpath("provenance.json").read_text(encoding="utf-8"))
for component in manifest["components"]:
    for item in component.get("selected_files", []):
        if "destination" in item:
            relative = item["destination"].removeprefix("src/negotiator/")
            assert (
                hashlib.sha256(package.joinpath(relative).read_bytes()).hexdigest()
                == item["sha256"]
            )
assert package.joinpath("web/static/index.html").is_file()
with tempfile.TemporaryDirectory(prefix="negotiator-install-") as temporary:
    cwd = Path(temporary)

    def cli(*args):
        result = subprocess.run(
            [sys.executable, "-m", "negotiator", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return json.loads(result.stdout)

    assert cli("doctor")["offline_demo_ready"]
    from negotiator.software import package_content_hash, runtime_identity

    assert runtime_identity()["package_content_sha256"] == package_content_hash(
        checkout / "src/negotiator", checkout / "provenance.json"
    )
    demo = cli("demo", "--output", "demo")
    assert cli("replay", demo["journal"])["outcome"]["reason"] == "agreement"
    assert cli("cite", "demo", "--format", "json")["papers"]
    import shutil

    shutil.copytree(checkout / "examples/reproduction", cwd / "recipes")
    assert cli("reproduce", "recipes/method.json", "--output", "method")["status"] == "verified"
    assert Path(
        cli("report", "demo", "--include-practice", "--output", "report")["report"]
    ).is_file()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    token = secrets.token_urlsafe(24)
    env = {**os.environ, "NEGOTIATOR_ACCESS_TOKEN": token}
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "negotiator",
            "gui",
            "--no-browser",
            "--port",
            str(port),
            "--data-dir",
            "records",
        ],
        cwd=cwd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                with urllib.request.urlopen(base + "/api/health", timeout=1) as response:
                    assert json.load(response)["status"] == "ready"
                break
            except (urllib.error.URLError, TimeoutError):
                if process.poll() is not None:
                    raise RuntimeError(
                        "Installed web server exited before becoming ready."
                    ) from None
                time.sleep(0.1)
        else:
            raise RuntimeError("Installed web server did not start.")
        request = urllib.request.Request(
            base + "/api/catalog", headers={"X-Negotiator-Token": token}
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            assert len(json.load(response)["domains"]) == 4
        with urllib.request.urlopen(base, timeout=2) as response:
            assert b"/assets/" in response.read()
    finally:
        process.terminate()
        process.communicate(timeout=10)
print("Fresh wheel: source hashes, domains, demo, replay, report and HTTP GUI passed.")
