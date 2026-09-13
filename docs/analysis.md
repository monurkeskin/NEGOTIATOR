# Replay, analysis and data exports

Use **Build report** in the conductor view after a session ends, then **Open report**
or **Download all files (ZIP)**. Reports are local, readable offline and rebuildable.
For scripts:

```bash
negotiator run examples/study.json --synthetic --output demo-output
negotiator report demo-output --output report-output
```

`negotiator replay path/to/events.jsonl` reads a canonical journal without changing
it. `report` accepts either one session journal or the root data directory. Use a
new output directory for every export; existing reports are preserved. A root report
keeps cohorts and domains separate. A GUI report contains the selected study record.

## What you get

| Artifact | Content |
| --- | --- |
| `index.html`, `standalone.html` | Overview, missing/planned sessions, participant pairs and figures; the standalone copy embeds figures |
| `analysis.json` | Full-precision values, exclusions, metric definitions, configuration and source snapshots |
| `records.xlsx`, `*.csv` | Sessions, offers, observations, questionnaires, pairs, participants, conditions, presentation records |
| `sessions/<id>/` | Source events + manifest, PNG/SVG/PDF figures and utility-space CSV |

Canonical allocation bids always describe the human's share. Agent utility uses
its complement, independently for each issue's total. Utility is stored on 0–1;
GUI scores are that same value ×100. Reports recompute and check utilities against
the actual bid/profile; they fail if the canonical record disagrees. Journal hashes
and configuration hashes are checked before analysis. The exported source snapshot
has its own SHA-256 and last-event sequence.

A session's original `software` receipt identifies the installed package bytes,
Python and package version. Report generation version/time are recorded separately.
Do not substitute current code identity for the code that created an older record.

## Units, pairs and missingness

The independent unit is the **participant**. Condition means first average repeated
sessions within participant, then average those participant values. Offers are
within-session observations. Pair tables enumerate condition pairs and retain
missing sessions/no-agreement utilities. For three conditions, all three pairwise
comparisons are described; there is no automatic significance testing.

Practice is excluded unless `--include-practice` is selected. Interrupted and
operator-ended sessions are excluded from condition summaries. Withdrawals remain
outcomes. Agreement rate counts eligible ended sessions; agreement utility uses
agreements only. Every exclusion remains visible in the session table. Synthetic
and human-study records must be analyzed separately.

Different cohorts and domains are not pooled automatically. In particular, a pair
of Holiday A/B sessions does not establish utility comparability merely because
both use a 0–1 scale. Use the participant/session tables with your prespecified
cross-domain analysis and report its assumptions. Do not interpret an empty default
pair table as proof that a participant failed to attend; inspect the planned-session
table and domain identifiers.

Questionnaires belong to the **study journal**, with explicit phase and target
session. They are not duplicated into session journals. This keeps an acknowledged
answer consistent if one storage write fails. Scheduled but unadministered items,
optional missing answers and recorded zero values remain distinct. Exact historical
instrument wording is not inferred from item counts.

## Metrics

- Agreement measures have separate names in JSON, the session CSV and the workbook:
  `utility_sum` is U_h + U_a; `utility_product` is U_h × U_a;
  `normalized_utility_product` divides that product by the maximum product across
  the session's complete outcome space. This last measure matches the definition
  used in the Embodiment 2023 paper. It is not the utility sum. Metric identifiers
  and formulas accompany every report. No agreement, an unavailable reference
  profile or a zero maximum product produce a null normalized score with a reason.
- Utilities, elapsed seconds, actor-grouped move categories and outcomes derive from
  canonical actions. Move threshold is explicitly .03, adapted from public NegoLog
  V2 at `f7a4f88`; it does not change strategy decisions or legacy exact move features.
  Every offer row records its report threshold and definition; each session also
  records that these deltas use its stored profiles. Solver's online categories use
  its then-current estimated opponent preferences and a zero threshold, with
  different tie rules. Report categories must not be substituted for those inputs.
  Invalid thresholds are rejected even in sessions with no comparable offers;
  non-finite deltas cannot be classified as observed moves.
- Pareto geometry uses known assigned/elicited reference preferences. Maximum sum
  is **social welfare**, not Kalai–Smorodinsky. Raw-product Nash and reservation-
  adjusted surplus Nash are separate. No feasible surplus outcome is null with a reason.
- CBOM error is computed after the session across the bounded outcome space. RMSE,
  tie-aware Spearman and Pearson use the reference human profile. Constant/short
  vectors make correlations undefined. MAPE is null if a reference utility is zero.
  Estimated profiles are not silently treated as ground truth. Model Pareto precision/
  recall compare outcome identities, including tied points. No report metric consumes
  the strategy's random state.
- Valence and arousal are separate series, extrema and missing counts. Sources,
  detection quality and missing reasons accompany observations. Missing points create
  gaps in plots. Self-report, model output and robot display state are distinct records.
- Presentation records separate attempts, SDK acknowledgements, failures and visible
  browser rendering. A returned SDK call does not prove human perception.

Figures use fixed utility/affect scales, marker/line differences as well as color,
explicit labels and accompanying data. No participant-level confidence interval or
p-value is fabricated from offer counts. Inferential analysis needs your actual
study design, participant dependence and planned exclusions.

## Damaged and legacy records

```bash
negotiator recover damaged-session/events.jsonl --output recovered-copy
negotiator import-legacy historical.csv --mapping columns.json --output legacy-import.json --arousal-overwritten
```

Recovery verifies a prefix, creates a **new** copy and records how many suffix bytes
were lost. An unfinished copied session becomes interrupted. Original damaged bytes
remain unchanged. A failed storage operation is never acknowledged as saved.

Legacy import needs an explicit field-to-column map, for example
`{"participant_id":"Participant","valence":"Max_V","arousal":"Max_A"}`.
Use `--arousal-overwritten` only for records affected by the known legacy mapping bug:
those values are unrecoverable, not a second copy of valence. Reported legacy
utilities remain unverified without original profiles. The importer does not invent
seeds, deadlines, actors, missing timestamps or a historical experiment identity.
Its output is a separate versioned observation format, not a new canonical session.
