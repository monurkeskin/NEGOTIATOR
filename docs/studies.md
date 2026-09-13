# Conduct a study

Start with a practice run on your own machine. The conductor controls configuration
and timing; the participant uses a separate restricted view. There are no mandatory
per-turn readiness phrases.

## Prepare

The four-step wizard collects participant/study identity and instructions, domain
and preferences, session sequence, then a review of the configuration. Use a
pseudonymous participant ID. Set practice explicitly: it is excluded from descriptive
study summaries unless requested.

Choose Holiday A (Accommodation, Destination, Events, Season), Holiday B
(Accommodation, Destination, Duration, Season), Fruits or Desert Island, or import
an XML/JSON domain. Each allocation issue has its own total. In all bids, quantities
mean the units the human keeps. Profiles use weights summing to 1 and value scores
between 0 and 1. The display multiplies utility by 100.

**Assigned** mode uses the entered profile; if you leave it at the supplied example,
it is a synthetic rank assignment, not a recovered participant preference. Inspect
and replace it for a real protocol. **Elicited** mode asks the participant to rank
issues and values before each session. The conversion rule and full-precision
profile are recorded. Opposing profiles use the documented paired issue swap and
value rotation, which is not guaranteed to maximize conflict.

Each condition can override the domain, assigned profiles, output device and
strategy. In JSON, use `human_profile`, `agent_profile`, `output`, and
`output_device` inside that condition. Device names refer to local profiles passed
with `--devices`, allowing two robots from the same family to remain distinct.

Practice stays first when main conditions reverse. `counterbalanced` alternates
forward/reverse order using participant index; it is **not** a complete Latin square
for three or more conditions. Set the explicit sequence required by your design.
Profiles stay attached to conditions, so protocols assigning profiles by session
position should use two explicit order files instead of automatic reversal.

## Start and monitor

Open the participant display on the second monitor. Review instructions and score
rules. Have the participant confirm their preference ranking if selected. Use
**Run preflight** for configured devices, then **Start session**. Policy preparation
occurs before timing begins. A configured hardware failure does not switch the
condition to a different output or policy.

The overview and offer history follow the committed server journal. The deadline
keeps running through input and presentation. There is no pause that silently
changes a timed trial. Record unusual events with **Save note**. If necessary, use
**End session with reason**; the result is operator termination, not agreement.
Browser refresh recovers the current snapshot. A server interruption is recorded
as an interrupted session and cannot silently resume the original trial.

## Questionnaires and repeated sessions

Configure items with an ID, wording, integer minimum/maximum, optional
`minimum_label`/`maximum_label`, required flag, source and phase:
`pre_study`, `pre_session`, `post_session`, `post_study`.
The same item set is scheduled for every matching session phase. Source wording,
reuse rights and validity are the researcher's responsibility. Synthetic example
items are not validated scales.

Pre-session answers target the upcoming session; post-session answers target the
session just ended. The study journal is authoritative for answers and protocol
transitions. Optional blanks and surveys never administered remain explicit in
reports. Practice is identified, including its questionnaire targets when
`include_practice` is enabled. Items that exclude practice do not create missing
response rows for those sessions. A skipped optional item stays null, never zero.
Labels such as “Strongly disagree” and “Strongly agree” are shown beside the
numeric endpoints and retained in the study journal and analysis exports.

At a result, continue through any scheduled questionnaire and break. Set
`break_after_seconds` on the preceding condition to enforce its minimum duration;
the next stage stays unavailable until that duration has elapsed. Follow the
paper-specific guide for the duration and questionnaire order.
The next session gets a new history, clock, strategy/model and input state.

## Configuration files

`examples/study.json` is a complete synthetic example. Run
`negotiator gui --study examples/study.json` to load it into the GUI. Each invocation
creates a new study plan. Configuration becomes immutable after the first start;
create a new study for methodological changes. The title/instructions can be
edited before the first start.

Use the [paper companion](papers.md) matching your method as a documented starting
point. These are maintained configurations with explicit limitations; a matching
paper title alone does not make a run a historical reproduction.

## End and export

Agreement, deadline, withdrawal, candidate exhaustion, operator termination and
interruption are distinct. Zero-offer sessions are valid records. After finishing,
**Build report** exports the selected participant plan. To combine participants
from a study, run `negotiator report local-data --output NEW_REPORT_FOLDER`.
See [analysis](analysis.md) for exclusions, paired records and cohort/domain handling.

## Published protocols and study purpose

For the distinction between files needed to run a new study and historical
analysis inputs, see [protocol requirements](protocol-requirements.md).

Import a companion configuration through **New study → Import a paper or study
configuration**. Demonstrations permit generated profiles; custom studies require
explicit assigned profiles or declared elicitation. Published-protocol mode requires
a pinned scientific configuration and its evidence requirements. Missing profiles,
changed participant instructions, unknown required assets or mismatched hashes block
Start and appear in the conductor workspace. Import/preview does not connect a robot.

Conditions may form contiguous practice/main blocks. Counterbalancing reverses
blocks as units; separate `position_profiles` keep the appropriate point table at
each main-session position. Configure `break_after_seconds` on the preceding
condition. The participant cannot skip a timed break; a restart conservatively
restarts it and records that fact. Main pre/post-session surveys exclude practice
unless `include_practice` is explicitly enabled.

Select **Ready, offer, then accept or reject** for the Jennifer notification protocol.
Ready and Reject are durable protocol events and do not increment offer history.
The gesture checkbox controls actual configured gesture delivery for that condition.
Mood policy parameters are available in imported configurations and are recorded.

## Target, reservation and game payoff

A score target is an aspiration displayed to the participant. A profile reservation
constrains acceptance. `reward_minimums` instead specifies that an agreement below
that threshold earns zero game points; it does not prohibit the agreement. These
are different experimental rules. Fruit-paper templates use a 40/100 reward threshold;
Jennifer's 30-point goal is not made into a hard acceptance constraint.

The log and report retain raw `utilities` and separate `payoffs`. Deadline has a
known zero game score; interrupted or unmeasured outcomes remain missing. The GUI
shows the game score when a reward rule is configured. Rounding affects display
only, including at the threshold boundary.
