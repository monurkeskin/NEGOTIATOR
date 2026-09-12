# Contributing

Start with [development](docs/development.md), the module map and worked custom
agent. Use a synthetic example to explain the behavior you want to change. For a
bug, add a failing behavioral test, fix the smallest responsible component, then
run the affected integration journey. Keep domain and strategy code independent
of UI/device SDKs; a UI update must not invent an unsaved action or result.

Preserve public API behavior, source notices, reference equations and file hashes.
Explain method changes separately from engineering corrections. A test fixture
or synthetic benchmark is not evidence of a human-study outcome. Keep participant
records, audio/video, credentials and machine-specific device settings out of Git.

Before a pull request, run Ruff, mypy, pytest with the branch gate, and a package
build. Rebuild and browser-test frontend changes. Include a concrete before/after
example, validation commands, dependency/runtime changes and known limitations in
the PR description. Hardware contributions need an exact runtime/device receipt
and the lab checklist; contract tests alone establish only software behavior.

The project is GPL-3.0-only. Retain required notices for third-party components.
Use GitHub issues for reproducible defects and discussions; do not attach human
study exports. Contributions can improve documentation, accessibility, domain
imports, protocol reliability, tests, device compatibility or published strategies.
