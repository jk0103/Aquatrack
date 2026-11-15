# Interpretation rules (interpretation 1.0, rules 2026.11-1)

Status: engineering baseline, Phase 3 (2026-11-15). The rules below decide what AquaTrack says
about a swim. They are deterministic and documented; none of them is a scientifically validated
judgement of technique. Code: `src/aquatrack/analysis/interpretation.py`.

## 1. Principles

- **A measurement is not a problem.** No rule fires because a value is high, low or different
  from a chosen number. There is no ideal angle, no technique score, and no comparison with
  other swimmers.
- **The swimmer is compared only with themselves:** their own cycles within a clip, and their
  own earlier compatible swims.
- **Metric availability is not interpretive validity.** A metric that passed its Phase 2 checks
  can still be barred from issue detection (section 3).
- **Missing evidence produces nothing.** Empty issue and priority lists are normal results.
- **Measurement limits are never technique faults.** They are reported in a separate list.

## 2. Three levels

| Level | What it is | Field |
| --- | --- | --- |
| 1 Observation | A statement about the measurements themselves | `observations` |
| 2 Issue candidate | A pattern in the swimmer's own swimming with enough evidence to be worth a look | `issue_candidates` |
| 3 Priority | An issue candidate that also repeats across swims or matches a goal the swimmer set; at most three | `priorities` |

Separately: `undetermined` (what could not be measured or judged, and why), `sessions` (earlier
swims and whether they were comparable), `rules` (what every rule did, including inactive ones).

## 3. Which metrics may be used for what

| Metrics | Observations | Compared with own history | May trigger an issue |
| --- | --- | --- | --- |
| cycle_duration, rhythm_variation | yes | yes | **yes**, when they passed their checks |
| stroke_rate | yes | yes | no (rule pending) |
| body_line_angle, leg_line_angle, head_height | yes | yes, unless either clip's camera view changed | no (rules pending) |
| pull_depth, elbow_angle_min, pull_path_variation | one "for information only" entry | no | no |
| cycle_time_change | yes | no | no |
| far-side arm, kick, breathing, rotation, left-right balance | not measured | - | - |

- Only metrics with status *reliable* count as evidence class `measured`. *Limited* metrics are
  shown as `context_only` and never trigger anything. *Unavailable* metrics appear only in
  `undetermined`.
- **Camera view.** When `coverage.view.status` is "changing": body-position observations become
  `context_only`, they are not compared with earlier swims, and the rhythm rule is suppressed
  (cycles filmed at an angle are timed less surely). The view check is a warning from apparent
  size, not a measured angle; apparent size also changes with distance, rotation, zoom and
  landmark errors. Nothing about posture is concluded from changes that follow the camera.
- Arm metrics are barred because Phase 2 left wrist placement at the end of the push unresolved
  and only a small share of the swim gives usable arm points.

## 4. Resolution: what counts as a difference

| Quantity | Smallest difference that counts | Why |
| --- | --- | --- |
| Cycle time | 2 video frames (0.08 s at 25 fps) | about one frame of uncertainty at each end of a cycle |
| Body line, leg line | 2 degrees | pose noise seen on the real clips |
| Head height | 0.05 trunk lengths | pose noise seen on the real clips |
| Rhythm variation | 2 frames as a share of the cycle time | below it, variation cannot be told from timing |

## 5. Observations (level 1)

| Id | Needs | Says |
| --- | --- | --- |
| obs.stroke_tempo | stroke_rate, cycle_duration | the tempo and the number of cycles |
| obs.rhythm | rhythm_variation, cycle_duration | the range of cycle times; "steady" when the variation is within timing resolution; how many cycles were clearly off the middle value |
| obs.tempo_through_the_clip | cycle_time_change | the change from the first to the last third |
| obs.body_line, obs.leg_line, obs.head | the metric | the value, and whether it stayed the same between cycles (spread within twice the resolution) |
| obs.arm_pull_context | any arm metric | the values, for information only |
| obs.history.<metric> | the metric reliable in this swim and in a compatible earlier one | "changed" or "no clear change", never better or worse |

Every observation carries its evidence, timestamps, limitations and what it does not claim.

## 6. Issue rules (level 2)

### timing.uneven_rhythm (active)
- Metrics: cycle_duration, rhythm_variation, both *reliable*.
- Minimum: 6 reliable cycles of one arm; a steady camera view.
- Logic: a cycle is off the rhythm when its time differs from the clip's median by more than
  3 frames **and** more than 10%. Triggers when at least 3 cycles and at least 25% of cycles are.
- Suppressed when the camera view changed; not applicable with fewer cycles or a limited metric.
- Wording: "worth a look at those moments". It does not say the rhythm is wrong.
- Limits: one clip; a breath, turn, push-off or change of pace all change a cycle.

### history.rhythm_less_steady (active)
- Metric: rhythm_variation, *reliable* in this swim and in the most recent compatible earlier swim.
- Logic: triggers when variation rose by more than twice the combined sampling error of the two
  values (each roughly value / sqrt(2(n-1)) for n cycles) plus the timing resolution.
  With about seven cycles per clip this is a high bar on purpose.
- Limits: two short clips; where in the length the clip was filmed changes the rhythm too.

### Pending validation (inactive, do nothing)
| Rule | What it would need before it may be switched on |
| --- | --- |
| pending.body_line_direction | a verified source for how body and leg line relate to drag or speed at the swimmer's level, and a check that the picture angle measures it |
| pending.head_position | a verified source on head position, and a head measure that separates lifting from turning to breathe |
| pending.stroke_rate_for_distance | swim speed or distance per stroke (not measured) and verified reference ranges per level and event |
| pending.arm_pull | arm points that can be trusted through the whole pull, and a second camera view |

These rules were reviewed against the evidence library in Phase 4
(`docs/EVIDENCE_LIBRARY.md`, "Review of the inactive interpretation rules"). The verified sources
do not support the interpretation any of them would make for AquaTrack's own measurements, so
all four stay inactive.

## 7. History

Earlier swims are the same swimmer's finished videos uploaded before this one. A session is
compared only if all hold; otherwise it is listed with the reason and not used:

- same stroke, same filming angle, same distance entry;
- same analysis schema version (metric definitions changed between 1.1 and 1.2);
- tracking not "insufficient" in either;
- stroke rate measured in both and within 20% (a sprint and an easy swim are different tasks).

No compatible session: the result is marked `baseline`. Nothing is said about causes, and a
change is never linked to race times.

## 8. Priorities (level 3)

An issue candidate becomes a priority candidate only if it holds against at least one earlier
compatible swim **or** matches a goal the swimmer set. Points, all visible in the result:

| Factor | Points |
| --- | --- |
| Evidence: reliable cycles behind it | 8+ = 2, 4+ = 1 |
| Repeated in the clip: share of cycles | 50%+ = 2, otherwise 1 when it is a per-cycle pattern |
| Seen across swims | 1 per earlier compatible swim it holds against, at most 2 |
| Your goals | 2 when it matches a goal on the profile, 3 when that is the main goal |
| Size against noise | 2 at twice the threshold, 1 at 1.5 times |
| Outside evidence | always 0: no effect on speed has been verified |

Sorted by points, at most three. Zero is common and is shown with the reason.

## 9. Personal context

Used: swim level, personal bests and the optional goals from `profiles/{uid}` (goal keys:
stroke_consistency, body_alignment, arm_technique, speed, endurance, breathing,
overall_freestyle; one may be the main goal); stroke, distance and filming angle from the
upload. A goal matters only when an issue candidate exists that its rule relates to: it then
lets that candidate be ranked (2 points, 3 for the main goal). A goal never creates a finding.
Level and personal best are recorded in the result but change no finding: no reference values
per level have been verified. Missing fields are never filled in. The swimmer's free-text note
and target time are not read here.

## 10. Storage and versions

One document per run at `videos/{id}/interpretations/{interpretationId}` (backend writes, owner
reads), with `interpretation_version`, `rules_version`, `analysis_id` and
`analysis_schema_version`. A run reads only the stored `AnalysisResult`, so results can be
interpreted again (`POST /videos/{id}/interpret`) without video, pose data or a model. Each run
adds a document; analysis documents and earlier interpretations are never changed. Analysis
results of schema 1.0 (no metrics) are read without error and yield no findings.

## 11. What is not validated

- Every threshold in sections 4, 6 and 7 is an engineering choice.
- On the two real clips no issue rule fired, so the active rules have only been exercised on
  synthetic data.
- Whether any pattern reported here relates to swimming speed or efficiency is unknown.
