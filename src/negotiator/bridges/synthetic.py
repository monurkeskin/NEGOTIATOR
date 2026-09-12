"""Offline protocol fixture; it never controls hardware or measures a participant."""

import time

from .protocol import serve


class SyntheticDevice:
    def call(self, operation, payload):
        if operation == "hello":
            return {
                "family": "synthetic",
                "runtime": "synthetic-1",
                "capabilities": ["speech", "gesture", "face", "transcript", "affect"],
                "assets": [],
                "hardware_tested": False,
            }
        if operation == "wait":
            time.sleep(10)
        if operation == "listen":
            return {
                "transcript": "Synthetic incomplete transcript",
                "source": "synthetic",
                "raw_recording": False,
            }
        if operation == "observe":
            return {
                "valence": 0.2,
                "arousal": -0.4,
                "emotions": {"Happy": 1.0},
                "source": "synthetic",
            }
        return {"delivered": True, "synthetic": True}

    def close(self):
        pass


if __name__ == "__main__":
    serve(SyntheticDevice())
