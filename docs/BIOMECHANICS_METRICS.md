# Biomechanics metric specification (analysis schema 1.2)

Status: engineering baseline, Phase 2 (2026-11-15). Checked on two real clips of one swimmer
(see `docs/PHASE2_VALIDATION.md`). Nothing here is scientifically validated, and no metric is a
judgement of good or bad technique. Thresholds are stated so they can be challenged, not because
they are proven.

Code: `src/aquatrack/analysis/metrics/cycles.py` (pulls and cycles),
`usability.py` (camera side, usable arm points), `biomechanics.py` (metrics and reliability),
`metrics/technique.py` (the student's existing geometry, reused), `pipeline.py` (assembly).

## 1. What existed and what it measures

| Module | What it actually measures | Use in 1.1 |
| --- | --- | --- |
| `cleanup.py` | Score cut-off, flipped frames, left/right swaps, impossible points, spikes, gap fill up to 0.2 s, light smoothing | unchanged |
| `processing.py` | Swimmer identity segments, joint states | unchanged |
| `cycles.py` | Arm cycles from the arm's angle around the shoulder | event detection rewritten (section 3) |
| `technique.py` | About 20 per-cycle geometric measures (elbow, catch, pull depth, reach, entry, body line, hip depth, head angle, kick, foot, breathing) | 4 measures reused; pull window fixed to the whole pull |
| `horizon.py` | Direction of travel: hip path, pool lines, or the frame | reused |
| `stroke_rate.py`, `symmetry.py` | Wrist-height peak counting and left/right wrist travel ratio, on raw wrist tracks | not used: they count drawn-in recovery points and the hidden far arm as real |
| `quality.py` | Tracking quality grade | cycle criterion removed (section 5) |

Measures in `technique.py` that are **not** exposed, and why:
head angle from the ear-to-nose line (swings 10-80 degrees inside a cycle on real clips because
the 2D line changes with head roll, so it mixes breathing with head lift: replaced by
`head_height`); catch and entry measures (depend on the recovery and entry, which an underwater
camera does not see); kick count, kick size, knee bend, foot point and breathing (computed, never
checked against video); hip depth (same information as the two alignment angles).

## 2. Four kinds of evidence, kept apart

1. **Model score.** How sure the pose model is. Used only by cleanup. A high score does not
   mean the joint was visible: on both real clips RTMW draws the recovering arm swinging back
   under the body with scores of 4 to 7 (cut-off 3.0).
2. **Support.** Per frame, each arm's elbow and wrist are in exactly one class (`ArmFrame`):
   - *supported*: the model's own points for shoulder, elbow and wrist, inside an underwater
     pull that was seen passing straight down (from where the arm leaves the front to the exit),
     with believable segment lengths. The only class arm metrics read. "Supported" by the
     movement; nobody has confirmed the arm was visible.
   - *interpolated*: elbow or wrist filled across a short gap. Never measured.
   - *model only*: the model placed the points and nothing backs them up: recovery in the air,
     behind the body, drawn stretched in front (reported separately, **not** a confirmed
     reach), or inside a pull with a collapsed segment. Never measured.
   - *rejected* / *missing*.

   The five shares add up to 100 and are reported per arm in `coverage.arms`. The word
   "observed" in the pose files (`JointState.OBSERVED`) only means "the model's point was
   kept"; the app calls it "placed by the model".

   **Collapsed segment:** inside a pull, an upper arm or forearm drawn shorter than half that
   arm's own median length in its pulls. A real arm does shorten in the picture when it points
   toward or away from the camera, so only this much (more than 60 degrees out of the
   picture) is ruled out, and only when at least 10 pull frames define "usual". Heuristic.
3. **Temporal consistency.** A pull is accepted only if the arm was in front, then passed
   straight down between two observed frames no more than 0.25 s apart, at no more than 900
   degrees per second, and was followed further back. Backward motion never counts.
4. **Metric usability.** Each metric names the joints, cycles and coverage it needs (section 4).

The raw and processed pose always keep both arms. Usability only decides what is measured.

**Camera side.** A face-down swimmer heading to the right of the picture shows the camera their
right side (left when heading left); backstroke is the other way round. That rule assumes an
unmirrored video and correct left/right labels, so it must be backed by the footage: the near
arm's pulls are followed at least 10 degrees further back (median), and/or its raw scores are at
least 0.5 higher. No supporting evidence, or evidence against: the side is "not established" and
arm geometry is unavailable. Only underwater side views are considered.

**Interpolated joints.** Points filled by cleanup (gaps up to 0.2 s) are never used by any metric
and never start or end a pull. They only keep the trunk length and the picture continuous.

## 3. Stroke segmentation

- Arm angle: wrist around the shoulder, from the hip-to-shoulder line. 0 ahead, 90 straight
  down, 180 back. Pull direction is "below the body" unless the clip clearly turns the other way.
- **Event:** the arm passes straight down (mid-pull). Chosen because it is the one moment an
  underwater side camera sees for both arms. The previous method (unwrapped angle, cycle ends at
  "straight back") lost cycles when the drawn recovery cancelled a pull and split them on wobbles.
- **Pull:** reach (hand furthest forward while in front), start (last frame within 45 degrees
  of straight ahead), mid-pull, exit (last frame followed moving back; 15 degrees of wobble
  allowed). Arm frames are *supported* from start to exit only: a glide in front is not.
- **Cycle:** one mid-pull to the next of the same arm.
  - *reliable*: at least 60% of its underwater frames have an observed shoulder and wrist,
    duration 0.6 to 4.0 s, and 0.6 to 1.6 times the clip's median cycle.
  - *ambiguous*: `merged` (too long: a pull was not seen), `fragment` (too short), `hidden`.
  - *partial*: before an arm's first mid-pull and after its last. Listed, never counted.
- **Timing arm:** the camera-side arm when established and it has reliable cycles, else the arm
  with more reliable cycles.
- **Terms.** One *cycle* is one full turn of one arm. Both arms make one *stroke* each per cycle,
  so strokes per minute (both arms) is twice cycles per minute. Only cycles are reported.
- **Count.** `cycle_count` is given only when every cycle of the timing arm is reliable and
  neither clip edge holds more than 1.2 cycles of swimming without a pull. It counts whole cycles
  between the first and last mid-pull seen, not strokes in a length.

## 4. Metrics

Shared rules unless stated: stroke freestyle, view underwater side; other strokes or views are
held at "limited" (breaststroke: unavailable). Per-cycle value = median over the cycle's usable
frames, needing at least 50% of them (minimum 3). Reported value = median over cycles, with the
25th-75th percentile. **Reliable** needs at least 3 cycles and 70% joint coverage; otherwise
**limited** with the reason. A geometric value that runs steadily in one direction through the
clip (rank correlation with time 0.8 or more, 4+ cycles) is limited: that is usually the camera
angle changing. Tracking grade "insufficient" makes everything unavailable.

**Camera view.** Geometric and proxy metrics leave out stroke cycles where the swimmer's trunk
is under 75% of its largest size among the timing arm's reliable cycles (`Metric.excluded_cycles`,
`coverage.view`). Reasoning: when a swimmer passes a camera that stays in place, the trunk's
size in the picture falls with the square of the cosine of the angle off side-on, so 75% is
roughly 30 degrees. This is not a measured camera angle. It sees nothing when the camera is
never side-on, moves with the swimmer at a fixed slant, or zooms; "steady" is not proof of a
side view. Timing metrics are not affected by the view and use every reliable cycle.

### stroke_rate - Stroke rate (temporal)
1 Element: stroke tempo. 2 Joints: shoulder and wrist of the timing arm, shoulders, hips.
3 Calculation: 60 / median duration of reliable cycles. 4 Unit: cycles/min. 5 Stroke: freestyle
(backstroke and butterfly use the same event, unchecked). 6 View: underwater side. 7 Coverage:
via the cycle rule (60% of underwater frames). 8 Interpolated: not used. 9 Reliable: 3+ cycles.
10 Unavailable: no reliable cycle. 11 Limits: a short clip covers few cycles.

### cycle_duration - Time per stroke cycle (temporal)
As stroke_rate. Calculation: median cycle duration, seconds. Timed to one video frame.

### cycle_count - Stroke cycles counted (temporal)
See section 3. Unit: cycles. Unavailable whenever a cycle is ambiguous or an edge hides a pull.

### rhythm_variation - Rhythm variation (temporal)
Element: steadiness of tempo. Calculation: sample standard deviation / mean of reliable cycle
durations of the timing arm, percent. Reliable: 4+ cycles; 3 is limited; fewer unavailable.
Limits: one frame is 1.6% of a 2.5 s cycle and 3.5% of a 1.1 s cycle at 25 fps, so smaller
differences cannot be timed; it does not say why the rhythm changed.

### body_line_angle - Body line angle (geometric)
Element: body alignment against the direction of travel. Joints: shoulders, hips, at least one
ankle. Calculation: direction of the best-fit line through shoulder midpoint, hip midpoint and
ankle (existing `technique.py`), against the travel direction from `horizon.py`. Degrees, 0 level,
positive feet lower. Reliable additionally needs a level reference: hip path or pool lines that
stay within 6 degrees. With the frame's own horizontal it is limited (a tilted camera shifts it).
Limits: picture angle; depends on the level reference.

### leg_line_angle - Legs against the trunk line (geometric)
Element: body alignment relative to the torso. Joints: shoulders, hips, at least one ankle.
Calculation: signed angle between the hip-to-ankle line and the trunk line carried on past the
hips. Degrees, 0 straight, positive legs below the line. Needs no level reference. Limits:
picture angle; the kick moves the ankles (median over the cycle).

### head_height - Head against the trunk line (geometric)
Element: head position relative to the body. Joints: nose, eyes, ears (at least 60% usable),
shoulders, hips. Calculation: perpendicular distance of the median face point from the trunk line
carried forward, divided by trunk length. Positive above the line. Unit: trunk lengths.
Limits: face points stand in for the head; the 2D trunk line shifts as the shoulders roll;
breaths are included; differences below about 0.05 are within pose noise.

### pull_depth - Pull depth (geometric, camera-side arm only)
Element: arm trajectory. Joints: shoulder, wrist of the near arm, *supported* frames only.
Calculation: largest depth of the wrist below the shoulder, perpendicular to travel (existing
`technique.py`). Unit: trunk lengths. Unavailable when the camera side is not established.

### elbow_angle_min - Elbow bend in the pull, 2D (proxy, camera-side arm only)
Element: elbow movement. Joints: shoulder, elbow, wrist of the near arm, *supported* frames
only. Calculation: smallest shoulder-elbow-wrist angle in the picture while the arm is 45 to 135
degrees from straight ahead (passing under the shoulder), from frames whose value is within 30
degrees per frame of a neighbouring frame, at least 3 such frames. Degrees, 180 straight.
The end of the push is left out because the hand is then at the hip and the surface, where on
real clips the model pulls the wrist up against the elbow. **Always limited:** a picture angle
is not the joint angle.

### catch_forearm_angle - Forearm angle at the catch, 2D (proxy, camera-side arm only)
1 Element: arm trajectory, early catch ("high elbow"). 2 Joints: shoulder, elbow and wrist of the
camera-side arm. 3 Calculation: for each pull, the moment the upper arm (shoulder to elbow) crosses
45 degrees below the direction of travel, between the pull's start and mid-pull; the forearm's
angle from straight down at that moment, interpolated between the two supported frames either
side (at most 2 frames apart). Positive: the hand is still ahead of the elbow. 4 Unit: deg.
5 Stroke: freestyle. 6 View: underwater side. 7 Coverage: as the other arm metrics; a pull gives
no value when its start was not followed (first supported frame already past 45 degrees) or the
frames around the crossing are not supported. 8 Interpolated: not used. 9 Reliable: never; it is
a picture angle and is always held at limited, like elbow_angle_min. 10 Unavailable: no pull
followed through the catch. 11 Limits: a forearm turned toward or away from the camera looks
more or less vertical than it is; one camera.
Why 45 and not 30 degrees: on the sprint clip the upper arm was already 31-40 degrees down at the
first supported frame of every pull, so a 30-degree catch fell outside what was followed.
Point accuracy (SWIM-360 dynamic, Apache-2.0: 370 human-labelled frames, every 100th video frame
of 9 freestyle swims by 7 swimmers, side-on underwater; RTMW-x given the labelled box): for an arm
labelled visible, elbow and wrist within 0.04 trunk lengths (median) and forearm direction within
2.4 degrees (median), 6.7 degrees (90th percentile). For an arm labelled hidden the points are
0.3-0.9 trunk lengths off and the arms are swapped in 41% of frames, while the model's score
barely separates the two (AUC 0.76): the reason only the camera-side arm's supported frames are
read. This checks points in single frames, not the metric on whole clips.
On saved pose of four public clips (not validated): Wellbrock 0.0, Effortless Swimming 0.6,
Khloptsov (clip titled 50 m freestyle) 50.4, the student's clip 26.5 degrees. When these values
were first recorded (2026-11-18) the frames behind them had not been looked at; the earlier
wording here said they had. A check was done afterwards (reported 2026-11-25,
`docs/FORM_STANDARD_NEXT_STEPS.md`): the arm was drawn on the 38 catch frames of five local
clips; the points follow the arm, with a visible forearm offset in a few Wellbrock frames. That
is a look at point placement on those frames, not a validation of the angle.

### pull_path_variation - Pull path variation (geometric, camera-side arm only)
Element: repeatability of the arm trajectory. Calculation: each pull's wrist path relative to the
shoulder, resampled to 20 points from the pull's start to its exit, RMS distance from that arm's mean path
(existing `technique.py`). Unit: trunk lengths. Needs 2+ pulls followed for 60% of their frames.
Limits: includes pose noise, so never 0.

### cycle_time_change - Cycle time, start to end (temporal)
Element: change across the swim. Calculation: median cycle time in the last third minus the first
third of the main swimming stretch. Needs 3+ reliable cycles in each third (9+ in all).
Limited when the change is within the cycle-to-cycle standard deviation. Never read as fatigue.

## 5. Not measured, and why

| Asked for | Why not |
| --- | --- |
| Left-right balance, arm coordination | Need both arms through whole pulls; the far arm is hidden from the side |
| Kick rhythm | Computed, not yet checked against video; far leg often hidden |
| Breathing timing | Head turn not reliably visible underwater from the side; unchecked |
| Body rotation | Needs a front or overhead view; no 3D from one side camera |
| Force, propulsion, efficiency score | Not measurable from joint positions |
| True joint angles | Only picture angles exist; labelled as proxy |

## 6. Quality levels (replaces the single grade)

1. Swimmer tracking: `quality.grade` (tracking only).
2. Camera view: `coverage.view` (steady / changing / unknown).
3. Arm points: `coverage.arms`, five exclusive classes; other joints in `quality.body_part_coverage`.
4. Stroke-cycle completeness: `coverage.cycles`.
5. Per-metric reliability: `metrics[].status`, with value, spread, cycles, cycles left out, coverage, timestamps, reason, limitations.
6. Overall coverage: `coverage.summary` and the three metric counts.

## 7. Schema

`ANALYSIS_SCHEMA_VERSION = "1.2"`. 1.1 added `metrics`, `coverage`, `stroke.partial`,
`stroke.counted_arm`, `stroke.counted_cycles` and `cycles[].kind`. 1.2 adds the exclusive arm
classes (`coverage.arms[].supported_pct`, `interpolated_pct`, `model_only_pct`, `rejected_pct`,
`missing_pct`, `model_only_in_front_pct`, `model_only_collapsed_pct`), `coverage.view` and
`metrics[].excluded_cycles`. Nothing was removed or renamed: the 1.1 arm fields (`followed_pct`,
`in_front_pct`, `unverified_pct`, `not_observed_pct`) are still written, 1.0 and 1.1 documents
load unchanged and are never rewritten, and the web app shows each in the layout it was made
for. `stroke.stroke_count` (two-arm total) is no longer produced. Pose files stay at schema 1.0
and are never modified by analysis.
