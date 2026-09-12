# Recompute, inspect and cite results

A run records what happened. A reproduction recipe states which input bytes,
calculation and comparison define a result. An independent empirical replication
requires a new approved study and is not performed by either command.

## A complete local example

```bash
negotiator run examples/study.json --synthetic --output demo-output
negotiator report demo-output --output demo-report
negotiator reproduce examples/reproduction/method.json --output method-output
negotiator reproduce examples/reproduction/paired.json --output paired-output
negotiator cite demo-output --format bibtex
```

Each output directory must be new. Read `index.html`, then inspect the corresponding
JSON/CSV instead of transcribing values from a plot. The method and paired inputs
are synthetic checks. Paper companions separately identify published point tables
and original result targets whose inputs remain unavailable.

## Recipe and evidence contract

A `ReproductionSpec` contains `paper_id`, `result_id`, `claim_scope`, named `analysis`,
input paths and SHA-256, parameters, environment and expected references with
absolute/relative tolerances. [JSON schema](../schemas/reproduction.json).
Only named calculations are allowed; a downloaded manifest cannot run shell commands.

| Calculation | Inputs | Result |
| --- | --- | --- |
| `profile-space` | Domain and two additive profiles | Every bid's two utilities, Pareto set size, welfare and raw/surplus Nash maxima |
| `method-vectors` | Explicit equation arguments | Quadratic target, Solver behavior or categorical affect values |
| `paired-summary` | One selected outcome per participant/condition | Complete-pair count, mean paired differences, participant bootstrap intervals and exclusions |

Expected numbers judge the calculated output; they do not enter the calculation.
The calculation reads only validated inputs and parameters. Missing input generates
`status: unavailable`, `results: null` and reasons. A discrepancy generates
`status: mismatch`. An empty comparison list is `computed-unchecked`, never verified.

| CLI exit | Meaning |
| --- | --- |
| 0 | Calculation completed; inspect verified versus computed-unchecked |
| 1 | Invalid configuration, input hash, environment or output path |
| 2 | At least one expected reference mismatched |
| 3 | Required input unavailable; no numerical result produced |

Results include full-precision JSON/CSV, a LaTeX table generated from those results,
applicable SVG/PDF figures and RO-Crate metadata linking inputs, software and outputs.
The table only rounds for display. The crate preserves identities and is not a grant
to redistribute input data; each input retains its own rights.

## Human studies and analysis units

Participants are independent units; offers are not. The paired recipe groups by
study, cohort and domain. Both conditions must exist once for the participant;
missing utility or a prespecified round threshold excludes the whole pair. Practice
is ignored. Domain mappings must be explicit and scientifically justified before
combining different tasks or score scales. The reported bootstrap resamples paired
participant differences with a recorded seed, not individual offers.

Define the outcome before preparing inputs: raw agreement utility, game payoff,
duration and an instrument response are different variables. Zero payoff after a
failed game is not a missing utility measurement. The `rounds` field requires a
recorded protocol-specific conversion; the journal's offer number is not silently
assumed to be a completed exchange. Historical significance tests require their
original design and analysis decisions; this generic recipe does not recover them.

## Version and citation identity

Every session and reproduction receipt records the engine version, package content
SHA-256, Python, platform and installed runtime dependencies. Study configuration
separately records protocol revision, method parameters, profile conversion and
score rules. Reward scoring is `threshold-reward-v1`; response-window aggregation
is `response-window-v1`; maintained strategy behavior is `maintained-2`.

`negotiator cite RUN_DIR --format bibtex` reads verified session journals and includes
papers associated with executed strategies and configured paper components. An
unstarted study does not contribute citations. Software entries retain the actual
run version/content hash. The preferred general citation remains the IJCAI paper;
CFF, BibTeX, CodeMeta and Zenodo metadata are generated from a common record.
