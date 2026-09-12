# Develop and test

The smallest extension is an object implementing `Agent.decide(Observation) ->
Decision`. [`examples/custom_agent.py`](../examples/custom_agent.py) shows the full
loop with a fixed-offer agent, own preferences and the canonical SessionRunner.
It uses no GUI, device or neighboring repository. Run it with
`python examples/custom_agent.py --output custom-demo`.

## Dependency direction

| Package | Owns | Keep out |
| --- | --- | --- |
| `domain` | Immutable issues, complete bids, profiles, actions and conversions | UI state, file handles, SDKs |
| `strategies`, `models` | Own-profile decisions, opponent observations, local RNG | Human reference profile, frontend state |
| `application` | Session/study transitions, timing, role projections, orchestration | Scientific inference from repeated turns |
| `events` | Canonical JSONL, sequence/hash checks, durable acknowledgement, recovery | Independent competing state stores |
| `interaction`, `adapters` | Draft interpretation, presentation, process contracts | Mutation of a committed bid |
| `analysis` | Derived descriptive records and figures | Policy tuning during the trial |
| `web`, `frontend` | Validated requests and role-specific displays | Unchecked writes, hidden agent data in participant payloads |

Prefer composition: supply an Agent to SessionRunner, supply a clock to Session
for deterministic timing tests, or configure a ProcessBridge. Extract an interface
when a current component needs it; do not add unused hierarchies. Public CBOM source
is kept verbatim, with type stubs and source hashes. Change its wrapper separately.

## Local commands

```bash
uv sync --locked
uv run ruff check src tests examples scripts
uv run mypy src/negotiator
uv run pytest --cov --cov-report=json:test-results/coverage.json
uv run python scripts/check_coverage.py test-results/coverage.json
uv run python scripts/check_sources.py
uv run python -m build
```

The coverage gate checks **branches**, separately for domains, session lifecycle
and policies/opponent-model adapter (90% each). The report also shows overall
coverage, including optional SDK branches and CLI subprocesses. Those figures have
different scopes; do not substitute one for the other or hide untested hardware.

For frontend development (Node 22+):

```bash
cd frontend
npm ci
npm run build
npm test
```

Install Chromium once using `npx playwright install chromium` if needed. Browser
tests start the real backend, exercise separate roles and save failure traces.
`npm run build` writes the assets shipped inside the Python package. Commit that
build with frontend changes; users of the wheel need no Node. CI checks that a
fresh build matches the committed assets.

## Worked test-first change

For a delayed request bug, first create two sessions in a test, retain the first
session ID, advance to the second, then send the old command. Assert the second
journal and GUI history are unchanged. Fix request validation at the application
boundary. Run the isolated test, session/protocol suite and the two-session browser
journey. A UI-only reset would not establish that the logger is correct.

For utility bugs, assert the same bid/profile gives the same full-precision value
in the Session event, replay and report. Include allocation complements and odd
rank counts. For deadline bugs, inject a clock crossing the boundary during work.
For device retries, assert exactly one formal bid and preserve unknown delivery.

## Releasing

Update version metadata, lock and built frontend, run all checks and a fresh wheel
installation outside the checkout. Verify source hashes, citation/relative links,
package assets and the actual three-OS CI result. Publish a versioned GitHub release
with wheel, sdist and SHA-256 checksums. Companion requirements pin a framework
commit and release; update them deliberately with their own independent test run.
No package is automatically published to PyPI.

## Reusable agent contract

```python
from negotiator.examples import builtin_domain, example_profiles
from negotiator.strategies import create_agent
from negotiator.testing import assert_agent_contract

_, own = example_profiles(builtin_domain("fruits"))
receipt = assert_agent_contract(
    lambda preference, seed: create_agent("hybrid", preference, seed=seed), own
)
assert receipt["deadline_checked"]
```

Use the same factory shape for an independent agent. The harness checks legal
complete offers, reservation, current-offer acceptance, deterministic retry,
local RNG and deadline behavior. It does not test scientific advantage. Prefer
composition over inheritance: the runner consumes only the Agent protocol, and
adapters exchange versioned messages rather than importing device SDKs into the core.

`reproduction` owns input validation, named calculation and comparison/export as
separate modules. Keep expected paper values out of calculation inputs. `metadata`
generates citation formats from `citation-metadata.json`; check all generated files
before publishing. A scientifically meaningful change requires its own source
locator, failing oracle, method/protocol revision and change-impact note.
