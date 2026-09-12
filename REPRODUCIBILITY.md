# Reproducibility statement

NEGOTIATOR 2.0.0 is a maintained implementation of the published framework and
selected published components. It is not a frozen recovery of any historical
human experiment. [paper-map.json](paper-map.json) links the framework's configuration
and component claims to code and tests; each [paper companion](docs/papers.md) owns
its own profiles, protocol requirements, equations and original-result availability.

Start with the [reproduction guide](docs/reproduction.md). Synthetic runs verify
software operation; published profile/equation checks verify those scoped methods;
original human-result recipes require permitted original inputs. Missing evidence
is shown rather than replaced by generated participants or fabricated numbers.

## Validation layers

- Unit and contract tests cover utility/perspective, strategy equations, notification
  stages, scoring, event durability, failure recovery, adapters and participant analysis.
- Real browser tests exercise conductor/participant workflows, preference elicitation,
  session reset, deadlines, timed breaks, missing protocol requirements and game scores.
- A wheel is installed and exercised outside the source checkout; metadata, distributed
  source hashes, CLI examples and the served GUI are checked in CI.
- Robot/SDK/model inference remains a separate [lab validation](docs/lab-validation.md).
  Process simulations and a successful handshake do not establish hardware behavior.

`uv.lock` and `requirements.lock` preserve the tested dependency resolution. Supported
CI environments are listed in the workflow and compatibility guide. Each run saves
actual dependency versions and code content hash, configuration, seed, conditions,
profile identity, observations and input missingness. No participant recording,
private working manuscript or proprietary SDK is part of the distribution.

Publication-aligned source review and static checks of selected public research
repositories informed this structure; those repositories' empirical findings were
not rerun. The practices follow the goals of the [NeurIPS checklist](https://neurips.cc/public/guides/PaperChecklist),
[AAAI reproducibility checklist](https://aaai.org/conference/aaai/aaai-26/reproducibility-checklist/),
[ICLR author guide](https://iclr.cc/Conferences/2026/AuthorGuide) and
[ICML author instructions](https://icml.cc/Conferences/2026/AuthorInstructions).
These are quality references, not venue certification or evidence of performance.
