"""Frozen FaceChannel inference in a separate, explicitly prepared camera runtime."""

import argparse
import platform
from importlib.metadata import version

from .assets import verify_assets
from .protocol import serve


def dimensional_output(prediction):
    """The original dimensional heads are ordered arousal, then valence."""
    import numpy as np

    array = np.asarray(prediction, dtype=float).reshape(-1)
    if array.size != 2 or not np.isfinite(array).all() or (abs(array) > 1).any():
        raise ValueError("Expected two bounded FaceChannel dimensional predictions.")
    return {"arousal": float(array[0]), "valence": float(array[1])}


class FaceDevice:
    def __init__(self, manifest, camera):
        self.manifest_path, self.camera_id = manifest, camera
        self.camera = self.detector = self.dimensional = self.categorical = None

    def call(self, operation, payload):
        if operation == "hello":
            import cv2
            import tensorflow as tf

            root, manifest = verify_assets(self.manifest_path)
            required = ["detector_config", "detector_weights", "dimensional_model"]
            if manifest.get("categorical_model"):
                required.append("categorical_model")
            if any(manifest.get(key) not in manifest["files"] for key in required):
                raise ValueError(
                    "Every configured model/detector must be in the asset hash manifest."
                )
            self.detector = cv2.dnn.readNet(
                str(root / manifest["detector_config"]), str(root / manifest["detector_weights"])
            )
            self.dimensional = tf.keras.models.load_model(
                root / manifest["dimensional_model"], compile=False
            )
            if manifest.get("categorical_model"):
                self.categorical = tf.keras.models.load_model(
                    root / manifest["categorical_model"], compile=False
                )
            self.camera = cv2.VideoCapture(self.camera_id)
            if not self.camera.isOpened():
                raise RuntimeError("Selected camera could not be opened.")
            return {
                "family": "facechannel",
                "runtime": "tensorflow-" + version("tensorflow"),
                "python": platform.python_version(),
                "capabilities": ["affect"],
                "camera": self.camera_id,
                "assets": list(manifest["files"]),
                "model_source": manifest["source_url"],
                "license": manifest["license"],
                "raw_recording": False,
                "hardware_tested": False,
            }
        if operation != "observe" or self.camera is None:
            raise ValueError("Camera/model preflight is required before observe.")
        import cv2
        import numpy as np

        success, image = self.camera.read()
        if not success:
            raise RuntimeError("Selected camera disconnected.")
        h, w = image.shape[:2]
        blob = cv2.dnn.blobFromImage(image, 1.0, (300, 300), (104.0, 177.0, 123.0))
        self.detector.setInput(blob)
        detections = self.detector.forward()
        faces = [d for d in detections[0, 0] if d[2] > 0.5]
        if len(faces) != 1:
            return {
                "source": "facechannel_frozen",
                "valence": None,
                "arousal": None,
                "missing_reason": "no_face" if not faces else "multiple_faces",
                "raw_recording": False,
            }
        detection = faces[0]
        x1, y1, x2, y2 = (detection[3:7] * [w, h, w, h]).astype(int)
        face = image[max(0, y1) : min(h, y2), max(0, x1) : min(w, x2)]
        if face.size == 0:
            return {
                "source": "facechannel_frozen",
                "valence": None,
                "arousal": None,
                "missing_reason": "invalid_face_crop",
                "raw_recording": False,
            }
        gray = cv2.resize(cv2.cvtColor(face, cv2.COLOR_BGR2GRAY), (64, 64)).astype("float32") / 255
        batch = gray.reshape(1, 64, 64, 1)
        result = dimensional_output(self.dimensional.predict(batch, verbose=0))
        if self.categorical is not None:
            labels = ["Neutral", "Happy", "Surprise", "Sad", "Anger", "Disgust", "Fear", "Contempt"]
            scores = np.asarray(self.categorical.predict(batch, verbose=0)).reshape(-1)
            if scores.size != 8:
                raise ValueError("Expected the eight-class public FaceChannel model.")
            result["emotions"] = dict(zip(labels, [float(v) for v in scores], strict=True))
        return {
            **result,
            "source": "facechannel_frozen",
            "detector_confidence": float(detection[2]),
            "raw_recording": False,
        }

    def close(self):
        if self.camera is not None:
            self.camera.release()
            self.camera = None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument(
        "--camera", required=True, help="Explicit camera index or local capture device path"
    )
    args = parser.parse_args()
    camera = int(args.camera) if args.camera.isdigit() else args.camera
    serve(FaceDevice(args.manifest, camera))
