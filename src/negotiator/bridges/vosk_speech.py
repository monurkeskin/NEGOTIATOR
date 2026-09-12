"""Optional local speech transcription, with an explicitly installed Vosk model."""

import argparse
import json
import platform
import queue
import time
from importlib.metadata import version

from .assets import verify_assets
from .protocol import serve


class SpeechDevice:
    def __init__(self, manifest, device, seconds=6):
        self.manifest_path, self.device, self.seconds = manifest, device, seconds
        self.model = None
        self.source = None

    def call(self, operation, payload):
        if operation == "hello":
            import sounddevice as sd
            from vosk import Model

            root, manifest = verify_assets(self.manifest_path)
            model_path = (root / manifest["model_directory"]).resolve()
            if not model_path.is_relative_to(root):
                raise ValueError("Model must be inside the verified asset directory.")
            observed = {str(p.relative_to(root)) for p in model_path.rglob("*") if p.is_file()}
            if observed - set(manifest["files"]):
                raise ValueError("Every model file must be covered by the asset manifest.")
            microphone = sd.query_devices(self.device, "input")
            sd.check_input_settings(device=self.device, channels=1, dtype="int16", samplerate=16000)
            self.model = Model(str(model_path))
            self.source = {
                "model_source": manifest["source_url"],
                "license": manifest["license"],
                "files": manifest["files"],
            }
            return {
                "family": "vosk",
                "runtime": "vosk-" + version("vosk"),
                "capabilities": ["transcript"],
                "python": platform.python_version(),
                "microphone": str(microphone["name"]),
                "assets": list(manifest["files"]),
                "raw_recording": False,
                **self.source,
            }
        if operation != "listen" or self.model is None:
            raise ValueError("Speech preflight is required before listen.")
        import sounddevice as sd
        from vosk import KaldiRecognizer

        audio = queue.Queue(maxsize=100)
        statuses = []

        def receive(data, frames, clock, status):
            if status:
                statuses.append(str(status))
            try:
                audio.put_nowait(bytes(data))
            except queue.Full:
                statuses.append("audio_buffer_full")

        recognizer = KaldiRecognizer(self.model, 16000)
        parts = []
        end = time.monotonic() + self.seconds
        with sd.RawInputStream(
            device=self.device,
            samplerate=16000,
            blocksize=4000,
            dtype="int16",
            channels=1,
            callback=receive,
        ):
            while time.monotonic() < end:
                try:
                    data = audio.get(timeout=min(0.5, max(0.01, end - time.monotonic())))
                except queue.Empty:
                    continue
                if recognizer.AcceptWaveform(data):
                    parts.append(json.loads(recognizer.Result()).get("text", ""))
        parts.append(json.loads(recognizer.FinalResult()).get("text", ""))
        return {
            "transcript": " ".join(p for p in parts if p),
            "source": "vosk_local",
            "raw_recording": False,
            "quality_flags": statuses,
            "model": self.source,
        }

    def close(self):
        self.model = None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--device", required=True, help="Exact microphone name or integer index")
    parser.add_argument("--seconds", type=float, default=6)
    args = parser.parse_args()
    if not 0 < args.seconds <= 10:
        parser.error("seconds must be in (0, 10].")
    device = int(args.device) if args.device.isdigit() else args.device
    serve(SpeechDevice(args.manifest, device, args.seconds))
