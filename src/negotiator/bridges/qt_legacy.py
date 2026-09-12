"""QT's ROS 1 /qt_robot service family; install roslibpy in its own runtime."""

import argparse
import platform
from pathlib import Path

try:
    from .protocol import serve
except ImportError:
    from protocol import serve


class QTDevice:
    def __init__(self, host, port, asset_root, timeout=10):
        self.host, self.port, self.asset_root, self.timeout = host, port, asset_root, timeout
        self.client = None
        self.services = {}

    def call(self, operation, payload):
        if operation == "hello":
            import roslibpy

            self.client = roslibpy.Ros(host=self.host, port=self.port)
            self.client.run(timeout=self.timeout)
            if not self.client.is_connected:
                raise RuntimeError("QT rosbridge did not connect.")
            paths = {
                "speech": "/qt_robot/behavior/talkText",
                "gesture": "/qt_robot/gesture/play",
                "face": "/qt_robot/emotion/show",
            }
            available = self.client.get_services()
            for capability, path in paths.items():
                if path in available:
                    actual_type = self.client.get_service_type(path)
                    self.services[capability] = roslibpy.Service(self.client, path, actual_type)
            assets = []
            if self.asset_root:
                for category in ("gestures", "emotions"):
                    root = Path(self.asset_root) / category
                    assets.extend(
                        str(p.relative_to(root).with_suffix("")).replace("\\", "/")
                        for p in root.rglob("*")
                        if p.is_file()
                    )
            return {
                "family": "qt",
                "runtime": "roslibpy-" + roslibpy.__version__ + ":qt-ros1",
                "python": platform.python_version(),
                "capabilities": list(self.services),
                "assets": sorted(set(assets)),
                "hardware_tested": False,
                "services": paths,
                "family_source": "observed_service_namespace",
            }
        if operation != "present" or self.client is None:
            raise ValueError("Preflight is required; operation must be present.")
        import roslibpy

        for capability, value, field in [
            ("face", payload.get("face"), "name"),
            ("gesture", payload.get("gesture"), "name"),
            ("speech", payload.get("text"), "message"),
        ]:
            if value:
                if capability not in self.services:
                    raise ValueError("QT is missing capability: " + capability)
                result = self.services[capability].call(
                    roslibpy.ServiceRequest({field: value}), timeout=self.timeout
                )
                if result.get("status") is False or result.get("success") is False:
                    raise RuntimeError("QT rejected the " + capability + " command.")
        return {"delivered": True, "acknowledgement": "ROS service calls returned"}

    def close(self):
        if self.client is not None:
            self.client.terminate()
            self.client = None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=9091)
    parser.add_argument(
        "--asset-root", help="Device-local data directory containing gestures/ and emotions/"
    )
    options = parser.parse_args()
    serve(QTDevice(options.host, options.port, options.asset_root))
