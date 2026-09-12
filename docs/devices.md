# Devices and presentation

The core runs on Python 3.11+. Device SDKs run in independent processes. The default
GUI, structured/text input and browser avatar need no hardware or external service.

| Adapter | Runtime contract | Validation in this release |
| --- | --- | --- |
| Text / browser avatar | Bundled web application | Real browser journeys; generated avatar, not the old video assets |
| NAO / Pepper legacy | Python 2.7, NAOqi 2.5 SDK; observed system version must match configuration | Transport and error contracts only; physical robot untested |
| QT legacy | ROS 1 `/qt_robot/` services; separate roslibpy runtime, historically 1.4.2 | Transport tests; service names/types inspected, physical robot untested |
| QT3 | ROS 2 `/qtrobot/` family | Not implemented by the legacy adapter |
| Local speech | Vosk + sounddevice and a hash-verified, separately licensed local model | Protocol/asset checks; microphone/model inference requires lab validation |
| Frozen FaceChannel | Separate compatible TensorFlow/OpenCV runtime, verified model and detector files | Head-order/asset tests; actual weights/camera inference untested |

A preflight receipt means the configured runtime answered. It does **not** certify
that a participant heard speech, saw an expression, or that a historical embodiment
was reproduced. Do the [lab checks](lab-validation.md) for your exact robot/image.

## Configure a device

Create a local `devices.json` from [the example](../examples/devices/legacy.example.json).
Paths are examples: point each command at the interpreter and script in your lab.
No shell command is evaluated. Never put credentials in command arguments.

```bash
negotiator bridge-files --output lab-bridges
negotiator gui --devices devices.json --data-dir local-data
```

The two legacy robot scripts can run directly from the exported bridge folder.
Newer input scripts run as modules with this package installed in their separate
interpreter, plus the chosen SDK dependencies. Do not install Python 2.7 packages
into the modern framework environment. There is no automatic SDK downgrade,
robot discovery, model download, or connection on import.

Select the output/input in the study wizard, then **Run preflight**. The receipt
includes observed runtime, capabilities and assets. Required gesture/expression
names must appear in the device's asset list. Missing capabilities stop preparation.
The NAO/Pepper family is operator-declared; confirm the actual robot identity in the
lab record. QT service types are discovered from rosbridge, avoiding the old
hardcoded service-type mismatch. QT's asset root must be visible to its bridge.

## Delivery and timing

Committed offers are immutable. A separate worker sends each agent offer and final
outcome. The journal distinguishes `presentation.attempted`, `.delivered`, `.failed`
and `.visible`. The last means a browser rendered the action while its document was
visible; it is not an eye-tracking or comprehension measurement.

The session clock continues during presentation. A participant cannot send the next
formal action while robot delivery is pending. Withdrawal remains available. A
failed/uncertain delivery is recorded and shown to the conductor; inspect and end
the session if the protocol cannot continue. The framework does not repeat an
uncertain hardware command, silently switch to text, or generate a replacement bid.
Driver acknowledgements mean SDK calls returned; the device may have its own
buffering. `request_elapsed_seconds` measures the monotonic interval around the
bridge request, including transport and SDK acknowledgement, even after termination.
It does not measure physical playback or participant perception latency. Preserve
this distinction in latency analysis.

Optional gesture/face maps select the published framework's utility/move-based
moods (Frustrated, Annoyed, Dissatisfied, Neutral, Convinced, Content, Worried).
The original thresholds and one-time deadline warnings are preserved. Presentation
RNG/wording never changes negotiation policy or canonical bids. Installed assets
are selected explicitly; proprietary or unresolved historical assets are not bundled.

## Speech and observations

Speech capture returns an editable transcript/draft. Check missing/ambiguous issues
and use **Send text** to commit a complete offer. Audio is held in memory for the
capture window, not saved. The Vosk bridge is a maintained local ASR option; it is
not claimed to reproduce an older experiment's recognizer.

For Vosk, the asset manifest needs `source_url`, `license`, `model_directory` and a
`files` map of relative paths to SHA-256. Every file under the model directory must
be covered. Pass `--manifest` and an explicit `--device` name/index to
`python -m negotiator.bridges.vosk_speech`. List microphones in that environment
with `python -m sounddevice`; install Vosk/sounddevice there, not globally.

The FaceChannel bridge uses frozen inference only. The manifest needs detector
config/weights and dimensional-model paths (optional categorical-model path), each
covered by `files`, plus provenance/license. Pass `--manifest` and `--camera` to
`python -m negotiator.bridges.facechannel`. It preserves grayscale 64×64, division
by 255, the original 0.5 detection threshold and **arousal, valence** head order.
No/multiple faces are explicit missing observations. Contempt remains in the log;
it has no categorical Solver coefficient and is excluded from its input without
renormalizing other class probabilities. Supply compatible verified weights before
claiming the adapter works with a particular model. No weights are bundled.

The conductor's camera preview is local browser video only. It records no frames
and does not run emotion inference. Manual affect, when explicitly selected, is
labeled participant self-report. Source, missingness, valence and arousal remain
separate in event records and reports.

## Primary interface references

- [NAOqi 2.5 Python SDK installation](https://doc.aldebaran.com/2-5/dev/python/install_guide.html)
- [QT ROS 1 API](https://docs.luxai.com/docs/api_ros), [QT ROS 2 API](https://docs.luxai.com/docs/v3/api_ros2)
- [roslibpy reference](https://roslibpy.readthedocs.io/en/latest/reference/index.html)
- [Public FaceChannel source](https://github.com/pablovin/FaceChannel)

Source-specific method differences and framework attribution are in [methods](methods.md)
and [provenance](../provenance.json). Hardware status must be updated from actual lab
receipts, independently of the software test suite.
