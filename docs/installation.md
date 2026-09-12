# Install and check NEGOTIATOR

Use Python 3.11+ in a project-specific environment. The standard installation
requires no database, message broker, Node, Docker or hardware SDK. Do not modify
an existing robot's Python environment to install the modern framework.

## Published wheel

Download the wheel from [v2.0.0](https://github.com/monurkeskin/NEGOTIATOR/releases/tag/v2.0.0),
activate a new virtual environment and run `python -m pip install PATH/TO/negotiator_human-2.0.0-py3-none-any.whl`.
Then run `negotiator doctor` and `negotiator gui`. Dependencies install from the
Python package index. There is no claim that this project itself is on PyPI.

## Locked source environment

With Git and [uv](https://docs.astral.sh/uv/) installed:

```bash
git clone https://github.com/monurkeskin/NEGOTIATOR.git
cd NEGOTIATOR
git checkout v2.0.0
uv sync --locked --no-dev
uv run --no-sync negotiator doctor
uv run --no-sync negotiator gui
```

`uv.lock` records resolved dependencies and hashes. Use `requirements.lock` as a
pip constraint file when installing a wheel into a separately managed environment:
`python -m pip install -c requirements.lock PATH/TO/WHEEL.whl`.
Python 3.12 is used for frontend development/type checks; CI tests the Python 3.11
minimum and 3.12 on three operating systems. Optional SDK environments have their
own compatibility requirements in [devices](devices.md).

## Local data and access

`negotiator gui --data-dir local-data --port 8765` stores records below that folder.
The terminal prints the conductor URL. Keep its access token private. Open the
participant link from the conductor; the server restricts the data returned to
that role. Local data includes preferences, transcripts, notes and questionnaires:
use pseudonyms and your study's approved retention/access procedures. Reports
contain these records too. Never upload participant exports as issue attachments.

The server uses `127.0.0.1`. A second window/monitor on the same computer works;
a second computer or phone is not part of this deployment. Do not bind it to a
public interface or treat its bearer tokens as a full hosted identity service.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `negotiator` not found | Activate the installed venv or use `python -m negotiator` |
| Port occupied | Start with `--port 8766` and use the newly printed URL |
| Browser did not open | Copy the printed conductor URL; `--no-browser` leaves it manual |
| Unauthorized page | Reopen the correct role link, including its token fragment |
| Server restarted during a session | The journal records interruption. Create a new trial; do not combine it with the interrupted one |
| No suitable offer | Check reservation/profile configuration and method notes; candidate exhaustion is a recorded ending |
| Import rejected | Check complete issue/value coverage, weights summing to 1, JSON/XML schema and 2 MB limit |
| Device preflight fails | Check its isolated runtime, exact version and installed assets; see the receipt and device guide |
| Report destination exists | Choose a new output folder; existing reports are preserved |
| Damaged final journal line | Preserve original bytes; use `negotiator recover ... --output NEW_FOLDER` and inspect recovery.json |
| Matplotlib cache is unwritable | Set `MPLCONFIGDIR` to a writable local folder before generating reports |

Installation downloads dependencies. After installation, the text/browser workflow,
synthetic runner, replay and reports operate without external services. Device
bridges connect only when configured and explicitly prepared.

CLI output and exported text files use UTF-8 on every platform, including pipes.
When collecting output from Python, use `subprocess.run(..., encoding="utf-8")`.
For a saved BibTeX citation, configure your editor to open UTF-8 so accented author
names remain intact.
