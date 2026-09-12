"""Append-only, hash-linked JSONL. An acknowledgement follows a successful fsync."""

import hashlib
import json
import os
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, cast


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class JournalError(RuntimeError):
    """A journal cannot be acknowledged or safely interpreted."""


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Serialize one store's writers across threads and processes on supported OSes."""
    with path.open("a+b") as stream:
        if sys.platform == "win32":
            import msvcrt

            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class Event:
    record_json: str

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.record_json))

    @property
    def payload(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.to_dict()["payload"])

    @property
    def kind(self) -> str:
        return cast(str, self.to_dict()["kind"])

    @property
    def sequence(self) -> int:
        return cast(int, self.to_dict()["sequence"])

    @property
    def request_id(self) -> str:
        return cast(str, self.to_dict()["request_id"])


class Journal:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._failed = False

    @classmethod
    def create(cls, directory: Path, manifest: dict[str, Any]) -> "Journal":
        directory.mkdir(parents=True, exist_ok=False)
        # The start event repeats configuration, so manifest and event can be checked together.
        try:
            with (directory / "manifest.json").open("xb") as stream:
                stream.write((canonical_json(manifest) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
            with (directory / "events.jsonl").open("xb"):
                pass
        except OSError as exc:
            raise JournalError(f"Could not create the session journal: {exc}") from exc
        return cls(directory / "events.jsonl")

    def _read(self) -> list[Event]:
        try:
            raw = self.path.read_bytes()
            if raw and not raw.endswith(b"\n"):
                raise JournalError(
                    "Journal has a truncated final record; preserve it for recovery."
                )
            result = []
            previous = "0" * 64
            session_id = None
            requests = set()
            for index, line in enumerate(raw.splitlines(), 1):
                record = json.loads(line)
                expected = record.pop("sha256")
                if digest(record) != expected:
                    raise JournalError(f"Journal hash mismatch at record {index}.")
                if (
                    record["schema_version"] != 1
                    or record["sequence"] != index
                    or record["previous_sha256"] != previous
                ):
                    raise JournalError(f"Journal sequence/hash chain mismatch at record {index}.")
                session_id = session_id or record["session_id"]
                if record["session_id"] != session_id or record["request_id"] in requests:
                    raise JournalError(f"Mixed session or duplicate request at record {index}.")
                requests.add(record["request_id"])
                previous = expected
                record["sha256"] = expected
                result.append(Event(canonical_json(record)))
            return result
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise JournalError(f"Invalid journal: {exc}") from exc

    def read(self) -> list[Event]:
        with self._lock, file_lock(self.path.with_suffix(".lock")):
            return self._read()

    def append(
        self,
        *,
        session_id: str,
        kind: str,
        payload: dict[str, Any],
        request_id: str,
        fingerprint: str,
        elapsed_seconds: float,
        expected_sequence: int,
    ) -> Event:
        if not request_id or len(request_id) > 200:
            raise ValueError("A request ID of at most 200 characters is required.")
        with self._lock, file_lock(self.path.with_suffix(".lock")):
            if self._failed:
                raise JournalError(
                    "Journal write failed; close the session and inspect durable records."
                )
            events = self._read()
            if len(events) + 1 != expected_sequence:
                raise JournalError(
                    "Journal changed in another writer; reopen it before proceeding."
                )
            if events and (
                events[0].to_dict()["session_id"] != session_id
                or any(e.request_id == request_id for e in events)
            ):
                raise JournalError("Mixed session or duplicate request; no event was written.")
            record = {
                "schema_version": 1,
                "session_id": session_id,
                "sequence": expected_sequence,
                "event_id": f"{session_id}:{expected_sequence}",
                "kind": kind,
                "request_id": request_id,
                "request_fingerprint": fingerprint,
                "elapsed_seconds": elapsed_seconds,
                "wall_time_utc": datetime.now(UTC).isoformat(),
                "payload": payload,
                "previous_sha256": events[-1].to_dict()["sha256"] if events else "0" * 64,
            }
            record["sha256"] = digest(record)
            text = canonical_json(record)
            try:
                with self.path.open("r+b") as stream:
                    stream.seek(0, os.SEEK_END)
                    offset = stream.tell()
                    try:
                        stream.write((text + "\n").encode())
                        stream.flush()
                        os.fsync(stream.fileno())
                    except OSError:
                        self._rollback(stream, offset)
                        raise
            except OSError as exc:
                self._failed = True
                raise JournalError(f"Event was not acknowledged: {exc}") from exc
            return Event(text)

    @staticmethod
    def _rollback(stream: BinaryIO, offset: int) -> None:
        try:
            stream.seek(offset)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
        except OSError:
            # Fail closed even if the disk also rejects recovery; never acknowledge this command.
            pass
