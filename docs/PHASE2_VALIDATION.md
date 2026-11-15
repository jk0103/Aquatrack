# Phase 2 validation on real video (2026-11-15)

Three public clips (sources and licences: `test_videos/public/SOURCES.md`, local only), real pose
data from the Phase 1 Colab export, unchanged. No new inference was run.

What kind of evidence each statement is:
**[calc]** computed by the pipeline; **[seen]** looked at by one person on frames;
**[annot]** manual annotation; **[assume]** engineering assumption. Nothing here is ground truth
or scientific validation: one annotator, one pass, two clips of the same swimmer.

## 1. Manual annotation

Method: contact sheets of plain frames, no pose overlay (every 3rd frame for the slow clip,
every 2nd for the sprint). Event: the arm points straight down under the shoulder. Arms told
apart by the watch on the swimmer's right wrist. Timing resolution 0.12 s and 0.08 s.

- Front Crawl Underwater (heading left, left arm near): left 1.80, 4.16, 6.68, 9.24, 11.76 s;
  right 0.48, 2.96, 5.40, 7.92, 10.44, 12.90 s.
- Sprint (heading right, right arm near): right 0.30, 1.44 (uncertain, in spray), 2.60, 3.64,
  4.68, 5.76, 7.00, 8.10, 9.16 s; left 2.04, 3.08, 4.12, 5.16, 6.44, 7.48, 8.60 s (left arm not
  separable before 2.0 s; swimmer out of frame 0.68-0.84 s).

## 2. Stroke segmentation against the annotation [calc vs annot]

Match tolerance = sheet step + one frame.

| Clip, arm | Annotated | Detected before | Detected now | Matched | Missed | Extra |
| --- | --- | --- | --- | --- | --- | --- |
| Front crawl, left (near) | 5 | cycles ok | 4 | 4 | 1 | 0 |
| Front crawl, right (far) | 6 | 2 split cycles | 6 | 6 | 0 | 0 |
| Sprint, right (near) | 9 | 1 merged cycle | 9 | 7 | 2* | 2* |
| Sprint, left (far) | 7 | 2 merged, 2 hidden | 7 | 5 | 2 | 2 |

\* The same two pulls, detected 0.2 s earlier than annotated (0.08 vs 0.30 s, 1.26 vs 1.44 s).
All nine near-arm pulls were found. In the first 1.5 s the swimmer is seen obliquely and tilted,
where "straight down in the picture" and "90 degrees to the body line" differ, and 1.44 s was
marked uncertain.

Reliable near-arm cycles: sprint 8 of 8 (Phase 1: 6 of 7 right-arm cycles, 8 of 13 over both
arms); front crawl 3 of 4. The missed one (11.76 s): the model put the left wrist above the body
for three frames with scores 4.9-7.2, so the crossing was not seen. The count is withheld for
that clip because 3.9 s of swimming follow the last pull that was followed.

Cycle time [calc vs annot]: front crawl 2.42, 2.55, 2.51 s vs 2.36, 2.52, 2.56 s; sprint median
1.13 s vs 1.09 s (largest single difference 0.12 s, inside the annotation resolution).

Far arm, sprint: still unreliable (the model twice draws it on top of the near arm). It is not
used for timing or geometry.

## 3. Hidden arms [calc + seen]

- After the hand leaves the water the model draws the arm swinging back to the front under the
  body: sprint 7.24-7.52 s, angle 178 -> 14 degrees in 8 frames, scores 4.0-7.2, states
  "observed". Old detector: merged two cycles. Now: those frames are "not verified", not used.
- Share of the swim, near arm: front crawl followed 39%, in front 47%, not verified 13%;
  sprint followed 57%, in front 16%, not verified 25%.
- Camera side: established on both clips from direction plus footage (near arm followed 33 and
  58 degrees further back). Kari clip: not established.

## 4. Metric values against the picture [calc + seen]

Lines drawn on the frames each metric points to (`experiments/phase2_validation/draw_metrics.py`).

- Front crawl: trunk, leg line and face point sit on the body in all 12 frames looked at. Legs
  visibly above the carried-on trunk line (value -8 degrees), feet lower than shoulders (body
  line 8 degrees), face on the trunk line (0.00). Near-arm points on the visible arm at the
  pull-depth frames.
- Sprint from about 2 s: same. Before that the camera sees the swimmer obliquely: body line 21
  degrees and leg line -21 degrees there, falling to about -1 by the end. Both are flagged
  "limited" by the drift rule. **Head height, pull depth and pull path variation of those first
  cycles are distorted too and are not flagged**: a known gap.
- Sprint 5.92 s: wrist placed short of the real hand at the end of the pull, giving an elbow
  angle of 97 degrees that the picture does not support. Elbow angle is always "limited".
- Interpolated joints: front crawl 1.5%, sprint 5.3% of limb joints; excluded from all metrics.

## 5. Rejection of unreliable measurements [calc]

- Kari clip (12.7% valid pose): all 11 metrics unavailable, no cycles, no camera side.
- Front crawl: count unavailable, rhythm limited (3 cycles), section comparison unavailable.
- Sprint: body line and leg line limited (drift), section comparison unavailable (3, 3, 2 cycles).

## 6. What broader validation needs

More swimmers, levels, body types and strokes; phone footage; a fixed side camera with known
level; frame-accurate event annotation by two people; reference measurements (calibrated
multi-camera or markers) before any angle is called accurate; a way to detect an oblique view.
Thresholds were set from physical reasoning and these two clips, and must be re-checked on new
footage before use in feedback.

## 7. Refinement after the side-by-side check (2026-11-15)

A three-panel comparison (plain frame, pose with joint classes, metric drawing) on 12 frames
(`experiments/phase2_validation/compare_pose_metrics.py`) showed four problems. Same pose files,
no new inference. Sections 3 and 4 above describe the state before this refinement.

| Problem [seen] | Change | Kind of fix |
| --- | --- | --- |
| Sprint 5.92 s: wrist drawn at the elbow as the hand leaves the water; that frame set the pull's elbow angle (97 degrees) | Elbow read only while the arm is 45-135 degrees from straight ahead; collapsed segments (under half the usual length) and values no neighbouring frame agrees with are left out | Definition change (confirmed for this frame) plus two heuristics |
| Front crawl 4.56 s: near arm in the air, its wrist drawn on the other arm, counted as "in front" (which read as seen) | "In front" is part of *model only*; arm frames are *supported* only from where the arm leaves the front | Classification change |
| Interpolated points inside pulls counted as "not verified" | Five exclusive classes that add up to 100 | Confirmed fix (tested) |
| Sprint first 2-3 s seen at an angle; only two metrics were flagged | Cycles with the trunk under 75% of its largest size are left out of every geometric metric | Heuristic; not a measured angle |

Values before -> after [calc]:

- Front crawl: body line 8.4, leg line -8.2, head 0.00, pull depth 0.74: unchanged. Elbow
  115.5 (3 pulls: 116.3, 115.5, 80.3) -> 115.9 (2 pulls; the third has too few usable frames
  under the shoulder, and its 80.3 came from the end of the push). Pull path variation
  0.13 -> 0.16 (the path is now compared from where the arm leaves the front, not from the
  reach). Arm coverage in pulls 97.8% -> 82.8%. View: steady (smallest size 95%).
- Sprint: 3 of 8 cycles left out (trunk at 38%, 55%, 69% of its largest size). Body line
  7.9 -> 1.5 and leg line -8.1 -> -6.8 (both still limited: they keep drifting in the remaining
  cycles); head -0.08 -> -0.09; pull depth 0.77 -> 0.75; elbow 110.3 -> 115.6; pull path
  variation 0.17 -> 0.16 (the two early values 0.34 and 0.32 are gone).
- Near-arm shares, front crawl: supported 10.7%, model only 79.0% (71.3% drawn in front),
  interpolated 7.0%, rejected 3.4%, missing 0%. Sprint: supported 35.0%, model only 46.2%
  (31.7% in front, 3.8% collapsed), interpolated 15.4%, rejected 1.2%, missing 2.2%.
- Timing metrics, cycle counts, camera side and the Kari clip: unchanged.

Still open [seen]:

- Sprint 5.92 s is not caught by the collapse rule (forearm at 51% of usual, rule is 50%). It no
  longer reaches the elbow metric because of the 45-135 degree rule. The 50% rule was not moved
  to catch it.
- Sprint 5.88 s now gives that pull's elbow value (99 degrees). The wrist is on the watch, the
  elbow point looks plausible, but the upper arm is foreshortened: whether 99 degrees is the
  real bend cannot be told from the picture. Elbow stays "limited".
- The view rule depends on the clip containing a side-on moment and on a camera that stays in
  place. The sprint's remaining cycles still drift (caught by the drift rule for two metrics).
- "Supported" is still inference from movement, not sight. A wrong point inside a followed
  pull with normal segment lengths passes.
