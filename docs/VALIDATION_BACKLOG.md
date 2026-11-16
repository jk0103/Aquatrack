# What has and has not been validated, and what data is still needed

Six different things are tested in this project. **None of them is evidence for another.**

| # | Kind of test | State today | What would count as done |
| --- | --- | --- | --- |
| 1 | Technical integration (upload, queue, worker, storage, screens) | Automated: unit, emulator and browser tests | The same on a staging deployment |
| 2 | Model inference (YOLO11m + RTMW-x produce pose for a video) | Done once per clip in Colab for 3 public clips; **never inside the worker, never on a new upload** | New videos processed by the deployed worker, outputs compared with reference runs |
| 3 | Pose quality (are the points right?) | Student's detector comparison; SWIM-360 figures; our gap-interpolation check on one clip | Labelled frames from our target footage; error per joint, especially arms under water |
| 4 | Biomechanical validity (do the metrics measure what they say?) | Cycle timing compared with manual annotation on 2 clips; geometry not validated against a reference system | Comparison with manual digitising or a motion-capture reference on several swimmers |
| 5 | Usability for real swimmers | None | Sessions with a handful of swimmers: can they film, upload, understand the result? |
| 6 | Training recommendation effectiveness | None | A study design; not claimable from software tests |

## Scientific-validation backlog

| Claim the product makes or implies | Evidence today | Needed |
| --- | --- | --- |
| A metric marked "reliable" is accurate | Internal consistency checks only | Category 4 above |
| The uneven-rhythm rule points at something meaningful | Fired only on synthetic data | Real clips where a coach's judgement and the rule can be compared |
| A change above the comparison threshold is a real change | Thresholds are engineering choices | Repeat recordings of the same swim to measure session-to-session noise |
| Pending rules (elbow, body line, and others) | Inactive | A verified source for each norm, then validation |
| Training activities help | Not claimed; sources are abstracts and coaching pages | Out of scope for software testing |
| Evidence library statements | 10 papers, abstracts only | Full texts read by someone qualified |

Wording review done in Phase 7 (no code change needed beyond those listed in the phase
report): reliability badges describe measurement status, not technique; goal-based plans say
no problem was found; comparisons use neutral words; completion counts are labelled as
practice the swimmer recorded; research is labelled as abstract-level; synthetic data is
labelled wherever it appears.

## Footage still needed (priority order)

1. The same swimmer, same camera position, same stroke and effort, on several days (at
   least 3 sessions, 6 or more cycles each): the only way to test comparison and progress.
2. Different swimmers at different levels, steady underwater side view.
3. Different resolutions and frame rates of the same swim.
4. Ordinary phone footage from the deck: a limited-support case that must be reported as
   limited, not measured.
5. Poor visibility, bubbles, occlusion.
6. Several swimmers in the frame, lane changes.

Conditions for collecting any of it: consent from each swimmer (and a parent for a minor), no
footage from a student's private Drive, no paid Colab runs, no identifiable footage in the
repository or in tests.
