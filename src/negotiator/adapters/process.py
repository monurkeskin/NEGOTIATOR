"""Versioned JSON-line transport to an independently installed device runtime."""

import json
import queue
import subprocess
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BridgeError(RuntimeError):
    """A selected device cannot satisfy its declared contract."""


class BridgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    command: list[str] = Field(min_length=1, max_length=30)
    family: str = Field(min_length=1, max_length=100)
    expected_runtime: str = Field(min_length=1, max_length=100)
    capabilities: list[str] = Field(default_factory=lambda: ["speech"])
    timeout_seconds: float = Field(default=15, gt=0, le=60)
    gestures: dict[str, str] = Field(default_factory=dict)
    faces: dict[str, str] = Field(default_factory=dict)

    @field_validator("command")
    @classmethod
    def valid_command(cls, value: list[str]) -> list[str]:
        if any(not item or "\0" in item for item in value):
            raise ValueError("Bridge arguments must be nonempty strings without NUL bytes.")
        return value


def load_devices(path: Path | None) -> dict[str, BridgeConfig]:
    if path is None:
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {name: BridgeConfig.model_validate(value) for name, value in raw.items()}


class ProcessBridge:
    def __init__(self, config: BridgeConfig):
        self.config = config
        self.process: subprocess.Popen[str] | None = None
        self._responses: queue.Queue[str | None] = queue.Queue(maxsize=16)
        self._lock = threading.RLock()
        self.receipt: dict[str, Any] | None = None

    def _read(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        try:
            while line := process.stdout.readline(1_000_001):
                if len(line) > 1_000_000:
                    break
                self._responses.put_nowait(line)
        except (ValueError, OSError, queue.Full):
            pass
        finally:
            try:
                self._responses.put_nowait(None)
            except queue.Full:
                pass

    def connect(self) -> dict[str, Any]:
        with self._lock:
            if self.process is not None:
                assert self.receipt is not None
                return dict(self.receipt)
            self._responses = queue.Queue(maxsize=16)
            try:
                self.process = subprocess.Popen(
                    self.config.command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                )
                threading.Thread(target=self._read, args=(self.process,), daemon=True).start()
                receipt = self.request("preflight", "hello", "hello", {})
                if (
                    receipt.get("family") != self.config.family
                    or receipt.get("runtime") != self.config.expected_runtime
                ):
                    raise BridgeError(
                        "Device family/runtime does not match the selected configuration."
                    )
                if not set(self.config.capabilities) <= set(receipt.get("capabilities", [])):
                    raise BridgeError("Device is missing a required capability.")
                required = set(self.config.gestures.values()) | set(self.config.faces.values())
                if required - set(receipt.get("assets", [])):
                    raise BridgeError(
                        "Configured gesture/expression assets are not available on this device."
                    )
                self.receipt = receipt
                return dict(receipt)
            except (BridgeError, OSError):
                self.close()
                raise

    def request(
        self, session_id: str, request_id: str, operation: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        with self._lock:
            process = self.process
            if process is None or process.poll() is not None or process.stdin is None:
                raise BridgeError("Device is disconnected; run preflight before a new session.")
            message = {
                "protocol": 1,
                "session_id": session_id,
                "request_id": request_id,
                "operation": operation,
                "payload": payload,
            }
            try:
                process.stdin.write(json.dumps(message, allow_nan=False) + "\n")
                process.stdin.flush()
                raw = self._responses.get(timeout=self.config.timeout_seconds)
                if raw is None:
                    raise BridgeError("Device exited before acknowledging the command.")
                response = json.loads(raw)
                if any(
                    response.get(key) != message[key]
                    for key in ("protocol", "session_id", "request_id")
                ):
                    raise BridgeError("Device response identity/protocol mismatch.")
                if response.get("ok") is not True:
                    raise BridgeError(str(response.get("error", "Device rejected the command.")))
                result = response.get("result")
                if not isinstance(result, dict):
                    raise BridgeError("Device returned an invalid result.")
                return result
            except queue.Empty as exc:
                self.close()
                raise BridgeError(
                    "Device timed out; delivery is unknown. No automatic retry."
                ) from exc
            except (OSError, ValueError, BridgeError) as exc:
                self.close()
                raise BridgeError(str(exc)) from exc

    def close(self) -> None:
        with self._lock:
            process, self.process = self.process, None
            if process is None:
                return
            if process.stdin:
                process.stdin.close()
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
            if process.stdout:
                process.stdout.close()
