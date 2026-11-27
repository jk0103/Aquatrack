# Hybrid advice (advice 1.0, prompt 2026.11-3, motion profile 1.1)

Owner's decision, 2026-11-27: the language model is no longer limited to rewording findings.
It interprets the swimmer's motion and proposes coaching hypotheses; the Python analysis
stays the authority for every measurement and checks every claim the model makes.

Status: implemented, unit-tested with a fake model, run end to end with three real model
calls on saved pose data (four in all). **Not validated for accuracy on real swimmers. Not deployed.**

## Flow

1. `analysis/motion_profile.py` builds the motion profile from the cleaned pose, the stroke
   cycles and the stored `AnalysisResult` (deterministic; its SHA-256 is stored with the
   advice). It holds the metrics with their status, each cycle's events and phase times,
   body-frame joint paths at 12 points of every cycle, elbow and knee angles, per-cycle
   series (median, range, trend, alternation), per-joint tracking gaps and the stated
   uncertainty. Up to 6 cycles of the followed arm; about 10 to 15 thousand tokens.
2. `analysis/advice.py` sends the profile, the swimmer's goals and level, and the list of
   library drills in one call (`gpt-6.2-astra`, reasoning effort high, strict JSON schema,
   `store=False`, no automatic retry). No video, frame, name, e-mail or free-text note.
3. Every piece of the answer is checked against the profile; a piece that fails is dropped
   and recorded in `rejected`, the rest is kept.
4. The result is one `Advice` document, `videos/{id}/advice/{adviceId}` (owner read,
   backend-only write). Its id is a hash of the analysis, the profile, the model, the prompt
   version and the advice version, so the same inputs are stored and paid for once.
   `POST /videos/{id}/advice` asks again on request and stores a new document beside the old.

## What is shown, kept apart

| Section | From | Meaning |
| --- | --- | --- |
| Coaching suggestions (at most 3) | model, checked | Ideas to try. Never a confirmed fault. Each has: what was noticed, why it may matter, what to try, a drill, what to check next time. |
| What looks consistent | model, checked | What the swimmer repeats well. Never a problem. |
| Measured in your movement | model, checked | Statements whose numbers are all in the profile. |
| General practice | training library, deterministic | Up to three activities for the swimmer's goals. Not based on anything found in the video; present even when nothing was suggested. |

The existing Feedback (observations, priorities, checkpoints) is unchanged and still shown.

## Checks (`advice.Checker`)

A statement or suggestion is dropped when it:

- states a number that is not in the profile (matched at the number's own precision);
- cites a metric that is unavailable, or a reference that is not in the data;
- refers to a time outside the clip;
- (suggestions) names no measurement, is supported by fewer than two stroke cycles or by
  more cycles than were measured, or is about joints usable in under 60% of the frames;
- prescribes an ideal angle, promises a result, or proposes breath-holding work.

An unknown drill id is removed without dropping the suggestion. More than three
suggestions: the first three are kept. The model's own confidence is stored and plays no
part in any check.

## Small samples: tentative suggestions

Short clips are common, and a model will find a pattern in three cycles. Such a suggestion
is kept, because it is still useful as something to look at, but it is marked `tentative`
by the checks (not by the model, and not as a confidence score) with the reason shown to the
swimmer:

- fewer than 4 trusted stroke cycles of the followed arm in the clip, or fewer than 4
  cycles supporting the suggestion (`MIN_CYCLES_FOR_FIRM`): "a first indication to check on a
  longer clip, not an established pattern";
- it cites phase timings (reach to catch, catch to mid-pull, mid-pull to exit, exit to next
  reach) whose whole spread across the cycles is under 3 video frames
  (`MIN_FRAMES_FOR_TIMING`): stroke events are placed to the nearest frame at both ends of an
  interval, so such a difference is at the limit of what the video can time.

The prompt (2026.11-2) also tells the model to count the trusted cycles, to word a pattern
from fewer than four as a first indication, and not to build a suggestion on a difference of
a frame or two. Both thresholds are engineering choices. On the three-cycle public clip the
one suggestion is marked tentative; on the sprint clip the reach-to-catch suggestion rests on
a 0.08 s spread at 25 fps and is marked tentative for the second reason.

## Exploratory evidence: the legs and the kick

The first real-inference run produced a suggestion about the kick ("the range of knee bend
narrowed from 63 to 47 to 26 degrees"). Traced back, it rested on one profile feature,
`knee_angle_range_deg`, which had two problems:

- it was computed from the 12 path samples of each cycle. The kick turns 12 to 16 times in
  one arm cycle of that clip, so 12 samples alias it: from every frame the three ranges are
  66, 54 and 48 degrees. The steep narrowing was an artifact of the profile, not movement;
- leg values are not measurements AquaTrack stands behind at all: `kick_rhythm` is listed as
  not measurable, the kick has never been checked against video, and the far leg is hidden.

Corrections (profile 1.1, prompt 2026.11-3):

- per-cycle values in `cycle_to_cycle` are computed from every frame of the cycle; the 12
  samples remain only as the path;
- the profile names its exploratory content (`motion.exploratory`: the features
  `knee_angle_range_deg` and `ankle_below_hip_line`, the sample fields for knee and ankle,
  and why);
- the checks set `evidence_basis = "exploratory"` on any suggestion filed under legs or
  citing one of those, which makes it tentative with the reason shown ("leg positions that
  AquaTrack does not yet verify as a measurement ... something to look at in your video, not
  a finding"), and sort it after suggestions that rest on measured values. It is kept, not
  removed;
- the prompt tells the model the same.

On the same clip with the corrected profile the model made no kick suggestion (one real
call). Evidence levels now in the output: measured statements; suggestions on measured
values; tentative suggestions (small sample or frame-limited timing); exploratory
suggestions (unverified leg tracking); and pieces that failed a check, which are not shown.

## The headline of a result

`resultHeadline` (frontend) chooses the page's title from the evidence there is: a measured
priority's own title; otherwise "N things to try from this swim" when AI suggestions exist
(with the sentence that these are suggestions, not a diagnosis); otherwise "No clear
technique issue in this clip", stated as a normal result. A short key above the advice
explains the three kinds of content: Measured, AI suggestion, General practice.

## Falling back

`source` is "deterministic" (no suggestion shown, general practice only, existing feedback
as before) when AI advice is not enabled, when no stroke cycle could be measured (no call is
made), when the call fails or times out, when the answer cannot be read, or when nothing
passes the checks. The reason is stored in `fallback_reason`.

## Settings (backend environment)

| Variable | Default | |
| --- | --- | --- |
| `AQUATRACK_ADVICE_PROVIDER` | off | `openai` turns it on; needs `OPENAI_API_KEY` |
| `AQUATRACK_ADVICE_MODEL` | `gpt-6.2-astra` | |
| `AQUATRACK_ADVICE_REASONING` | `high` | |
| `AQUATRACK_ADVICE_MAX_OUTPUT_TOKENS` | 40000 | includes reasoning tokens |
| `AQUATRACK_ADVICE_MAX_CALLS_PER_DAY` | 100 | per process |

Each analysed video with at least one trusted cycle makes one billed call. Measured on
three real calls: 9,600 to 14,700 input tokens, 1,800 to 3,200 output tokens (700 to 2,000
reasoning), about US$0.15 to 0.24 per video at list price, 40 to 80 seconds.

## Evidence and limits

- Experiment (`experiments/gpt_motion_advice/v2`, 2026-11-27, stopped early): with this
  model and profile, four of five patterns planted in synthetic swimmers were reported in
  every one of three runs (the existing rules: one of five), none was reported for three
  steady controls and two unusable-data cases, and no number outside the input was stated.
  A slow drift of the hips was missed in all three runs. Synthetic swimmers are simple
  geometric figures: this is not evidence of accuracy on real swimming.
- On real clips there is no ground truth. A suggestion being repeated across runs shows
  consistency, not correctness.
- The number check cannot tell a correct number from one that merely coincides with some
  value in the profile, and it does not check that a number is attached to the right thing.
- The checks cannot verify the reasoning that links an observation to a suggestion. That is
  why suggestions are labelled as AI suggestions and never as findings or priorities, and
  why they do not feed the training planner.
- Because a job is marked finished before the advice call starts, a slow answer cannot
  expire a lease or time the job out; the worker is busy for those 40 to 80 seconds, so the
  next queued video waits that long.
- Conditions not tested: video frames as input, a multi-step workflow, other models in the
  application.
- The reference to "no coach has reviewed this swim" must stay in the interface.
