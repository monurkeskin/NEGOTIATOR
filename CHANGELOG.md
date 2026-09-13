# Changelog

## 2.1.0 — 13 September 2026

Questionnaires preserve optional labels for the two scale endpoints in the GUI,
journal and analysis exports. API ratings must be integers or null; booleans and
coerced text/float values are rejected. Practice-only omissions no longer appear
as missing responses for instruments that exclude practice. Legacy configurations
without endpoint labels keep their protocol fingerprint. This fixes exported
missingness counts without changing existing recorded responses.

Session reports export the agreement utility sum, product and normalized product
as separate, versioned measures in JSON, CSV and Excel. The domain maximum is
computed from the recorded reference profiles; absent agreements or undefined
normalization remain null with a reason. Reports preserve the original journal.

Movement settings are validated before report generation, including sessions with
no offers. Non-finite utility differences are rejected. Offer exports record the
report definition and threshold separately from Solver's online move features.

Jennifer studies can record a social `offended_threshold` independently of the
preference reservation. Low offers can elicit Offended without making a subsequent
agreement invalid. Journals without the new parameter replay their original
reservation-based mood behavior. The companion protocols select 0.3 explicitly;
warning times and mild multipliers are unchanged.
Direct Python session construction now validates presentation settings before
creating a journal, using the same rules as the GUI study configuration.

Protocol requirements distinguish inputs needed to execute a new session from
records needed for historical analysis. Unclassified requirements still default
to execution; required session/calibration assets remain blocking. The six companion
packages now classify runtime materials and historical evidence separately.

Terminal presentation now follows the committed outcome for either accepting
actor: agreement uses Happy (generic) or Acceptance/Satisfied (Jennifer), including
after replay. Non-agreement endings no longer reuse a mood from a previous offer.
The journal's agreement, bid and utility calculations are unchanged.

English resource requests accept number words from zero to twenty and require a
complete human-share allocation. Unsupported recipient, negation and quantity
wording remains a draft instead of producing a guessed bid. `Agree` and `I agree`
use the existing current-offer acceptance checks. These changes extend and harden
the maintained input contract; they do not establish errors in historical studies.

## 2.0.0 — 12 September 2026

Adds independent paper contracts, exact published point profiles, purpose-aware
study preparation, practice/main blocks, timed durable breaks, position-specific
profiles and the Jennifer ready/offer/response protocol. Missing historical assets
stop preparation rather than selecting an illustrative replacement.

Separates raw utility, score targets and thresholded rewards: an agreement below
the fruit studies' 40-point target remains legal and gives zero game reward.
Corrects the 2025 Solver adaptation order and post-threshold Nash comparison,
versioned as `maintained-2`; undocumented historical constants remain explicit
maintenance choices. Affect uses the current response window, while retries use
the pending decision and committed presentation state.

Adds hashed reproduction manifests, participant-level paired analysis examples,
profile and equation recomputation, full-precision CSV/JSON, LaTeX tables,
SVG/PDF figures, RO-Crate manifests and executed-component citations. Paper maps,
independent companion guides and reusable agent contracts support contribution.

This release replaces the initial distribution with a clean source history while
preserving original licenses and attribution. It does not recreate unavailable
human-study inputs, establish hardware compatibility or claim new empirical results.

## 1.0.0 — 12 September 2026

Initial maintained release with a local conductor/participant GUI, five published
policy presets, pinned public CBOM, categorical/allocation domains and isolated
optional device bridges. Canonical session/study journals drive replay and offline
reports. Includes per-session preferences/output configuration, explicit missingness,
recovery copies, synthetic examples, contributor documentation and paper companions.

Corrected behavior includes issue-preserving bid identity, arbitrary odd/even rank
counts, full-precision weights, nonnegative terminal clocks, session-history isolation,
last-offer acceptance, durable questionnaire targeting, stale command rejection,
independent arousal/valence records and camera cancellation. Report calculations
preserve participant dependence, cohorts and domain differences.

This is a maintained implementation, not a historical experiment snapshot.
Physical robot and model-inference support require the documented lab checks.
