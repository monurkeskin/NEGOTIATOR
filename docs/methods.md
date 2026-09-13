# Methods and implementation provenance

This is a maintained implementation of published negotiation components. It is
not a frozen copy of the software used to collect any historical human-study data.
Configuration, utility profiles, seeds, code version and exact actions are saved
with each new session. Synthetic examples demonstrate operation only.

## Strategies

| Preset | Policy | Initialization and adaptation |
| --- | --- | --- |
| `hybrid` | Quadratic time concession, then reciprocal behavior mixed by elapsed time squared | First two received offers use the time component; later offers use actual preceding agent utility |
| `solver-2021` | Solver categorical emotion/awareness equation | Behavior from the second received offer; sensitivity after eight received offers; awareness in [0,1]; repeated selfish transitions multiply the response factor by 1.5 |
| `solver-2025` | Published categorical equation, current-decision adaptation and estimated Nash comparison | Behavior from the second received offer; configurable adaptation threshold (default 9), unclipped awareness ratio with explicit zero-denominator handling |
| `tsbt` | Stochastic bids within two quadratic utility curves | Lower control points [.94,.5,.4], upper [1,.9,.7]; an empty interval expands by .01 with a finite bound |
| `babt` | Reciprocal utility change scaled by .5+.5t | Initial target .95; nearest feasible utility thereafter; no utility change preserves the previous bid |

Hybrid and Solver use time control points [.9,.7,.4]. Differences are ordered
oldest to newest in a window of at most four: [1], [.25,.75], [.11,.22,.66], or
[.05,.15,.3,.5]. The three-difference weights sum to .99; they are intentionally
not renormalized. Elapsed time is monotonic and normalized to [0,1].

The categorical weights are Sadness −.33, Anger −.165, Neutral 0, Happiness .165,
Surprise .33; Fear and Disgust contribute 0. Missing affect remains explicitly
missing in diagnostics. A policy with no observation has no affect contribution;
this is not a claim that the participant was neutral.

For previous agent utility `u`, recent weighted utility difference `delta`, elapsed
fraction `t`, awareness `a` and categorical emotion effect `e`, the Solver behavior
target is `u + a² e − (1 − a²)(.5 + .5t) delta`. The final target mixes this behavior
target with the time target using weights `1 − t²` and `t²`.

The anonymized source linked by the later paper is an IJCAI framework snapshot,
as clarified by the maintainer. Its valence/arousal change rule is not evidence
that the IVA experiment used that rule. The Solver papers describe categorical
emotion, also confirmed by the maintainer and the earlier categorical source.
Both Solver presets use that representation. Historical experiment identity
cannot be inferred from repository HEAD or a branch name.

## Maintained corrections and explicit differences

- All strategies receive their own preferences and observations. The opponent
  model is the pinned public CBOM model; true human preferences are never supplied
  to a strategy. This is an explicit maintained model choice, not evidence that
  every historical study used this exact implementation.
- Acceptance uses the generated next bid's utility, with an inclusive equality
  boundary and reservation check. An acceptance references the pending offer ID.
  Uncommitted generated bids and acceptances are not appended as fictitious offers.
- Hybrid/Solver select among the first three feasible bids strictly below their
  target, preserving the current framework's selection convention. If none exist,
  the agent accepts a sufficient feasible received offer or ends with candidate
  exhaustion. It does not loop forever or offer below its reservation.
- Actual preceding offers determine reciprocal utility. A target is not substituted
  for the utility of a different executed bid. Solver's earlier source contains a
  separate descending estimated-Nash schedule not specified in the cited short
  paper's equations; that earlier schedule is not part of `solver-2021`. The 2025 preset instead follows the later paper’s explicit maximum-product offer comparison after adaptation.
- Six move features preserve the order silent, nice, fortunate, unfortunate,
  concession, selfish. Class labels are standard, silent, selfish, fortunate,
  concession. Classification uses the released fixed centers and Euclidean nearest
  center, with the first center resolving an exact tie; there is no fitting at startup.
- Move utilities use the offerer's perspective, including per-resource complements.
  Awareness retains the legacy category-change lag with bounds for short histories.
  It measures responsiveness in this policy, not statistical confidence.
- Constructors do not connect hardware. Each session owns its model, RNG, history
  and input state. Repeated delivery of a request cannot create a second action.

## References and source pins

- Framework: Keskin et al., *NEGOTIATOR: A Comprehensive Framework for Human-Agent
  Negotiation Integrating Preferences, Interaction, and Emotion* (IJCAI 2024).
  [Paper](https://doi.org/10.24963/ijcai.2024/1012).
- Framework reference code: [HumanRobotNego](https://github.com/berkbuzcu/HumanRobotNego/tree/0a2dd11ad324a057e7af9d2cd1cdccbf4c7bf499), GPL-3.0.
- Anonymized IJCAI framework reference: [human-agent-negotiation-framework](https://github.com/anonimpanda/human-agent-negotiation-framework/tree/90e4a3ab7120b781b28895b7109bcfbab663e05a), MIT; its notice is retained in `licenses/`.
- CBOM: [released opponent-model code](https://github.com/monurkeskin/CBOM/tree/41345ae4fee8c95c0dd641c7b80a43eb015422da),
  [method notes](https://github.com/monurkeskin/CBOM/blob/41345ae4fee8c95c0dd641c7b80a43eb015422da/docs/method.md)
  and [paper](https://doi.org/10.1007/s10489-023-05001-9). Only the Python opponent
  model and profile component are bundled. CBOMAgent's strategy is not used here.

CBOM's exact aggregated evidence and rank-sum issue weights follow that public
revision. They differ from an earlier recursive formulation; refer to its method
notes for the equivalence scope. File hashes and selected assets are listed in
[`provenance.json`](../provenance.json). Original notices are preserved in
[`NOTICE`](../NOTICE) and `licenses/`.


## Presentation behavior in 2.1.0

The generic mood schedule follows the inspected legacy implementation; it is not
identical to every paper's presentation specification. The Embodiment paper gives
.40/.60/.80 warning times, while this code variant uses .60/.73/.86. Keep the method
and protocol revision with a run when comparing those variants.

Terminal moods now follow the committed outcome for either accepting actor.
The generic policy selects Happy at agreement; Jennifer's policies retain their
own Acceptance/Satisfied names. This corrects a presentation defect without
changing the recorded agreement or utility. Jennifer's `offended_threshold` can
be set independently of reservation; absent settings preserve legacy behavior.
The revised companion protocols select 0.3 explicitly.

The text interpreter accepts complete English human-share requests with digits or
number words. Negated, approximate, fractional or partner-share wording requires
clarification. This maintained input contract does not recover the full historical
speech grammar. Verify the displayed allocation before sending a text draft.

## Scientific changes in 2.0.0

The 2025 paper's Algorithm `alg-solver` applies adaptation before generating the
current offer. Version 2.0 follows that order, implements the Silent direction from
`tbl-sensitivity`, and compares the generated bid with the estimated maximum-product
bid, choosing it only when own utility increases. These changes can alter offers
and outcomes; results from different maintained versions must not be silently pooled.

Unreported numeric choices remain explicit in `strategy_parameters`: adaptation
minimum 9 human offers, concession step .2, Silent multiplier .5, Selfish multiplier
1.5. The threshold, concession step and Selfish factor inherit maintained conventions; the Silent magnitude is
an explicit maintenance choice rather than a recovered experiment parameter.
The class-change trigger, four-difference weights, one-move awareness lag and
zero-denominator value 0 are also recorded/documented. Historical parameter
provenance is separate from the inputs needed to run a new study; see
[protocol requirements](protocol-requirements.md). See the 2025 companion
for equation/figure/algorithm locators and independent tests.

In the maintained 2025 preset, a transition to Silent sets the response multiplier
to .5. This reduces the magnitude of the reciprocal term without reversing its
sign. A zero utility difference still contributes zero. The paper specifies the
direction, but the inspected categorical source leaves this branch unchanged;
.5 is a declared maintenance choice, not a recovered experimental constant or an
empirically optimized value. Repeated decisions in the same class do not halve it
again. The earlier 2021 preset retains its separately documented adaptation rule.

Categorical affect is averaged over observations between the previous agent offer
presentation attempt (or offer commit if no attempt exists) and the human response.
`frame_count` weights aggregated observations. Frames outside the interval do not
carry forward. Missing frames remain missing; ignored emotion mass is not normalized
into other categories. A pending decision survives a failed journal write unchanged.

Jennifer's optional paper mood policies expose warning and mild thresholds rather
than claiming unpublished numeric values. A fresh replay of committed actions builds
the mood state, so failed presentation writes cannot consume a warning. Its
Ready/Offer/Response stages are separate from formal bids. A gesture-disabled
condition suppresses the gesture command while preserving speech.

Paper profiles now distinguish raw utility, a displayed target, a hard reservation
and a thresholded game score. In the fruit papers, accepting below 40/100 remains
possible and yields zero game points. These score rules are logged and checked by
analysis independently of raw agreement utility. No original human outcome is
recomputed without the permitted input and historical analysis identity.
