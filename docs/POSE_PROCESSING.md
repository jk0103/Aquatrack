# Pose processing and quality control (analysis v1)

How raw pose becomes something the app is willing to measure from. Code:
`src/aquatrack/analysis/processing.py`, `analysis/pose/cleanup.py` (the student's module,
unchanged), `analysis/quality.py`, `analysis/pipeline.py`. Contracts: `src/aquatrack/contracts.py`.

## Data kept at each step

| Object | What it is | Where it is stored |
|---|---|---|
| RawPose | Model output exactly as produced: frame number, timestamp, target box, box confidence, how the target was chosen, 133 points with raw scores, model names and config, video SHA-256 | Storage `analysis/{uid}/{videoId}/{analysisId}/raw_pose.npz` |
| ProcessedPose | Cleaned points; every point is observed, interpolated, rejected or missing, with reason flags | Storage `.../processed_pose.npz` |
| AnalysisResult | Stroke timing, quality report, what could not be measured and why | Firestore `videos/{id}/analyses/{analysisId}` |

Raw data is never edited. Legacy `.wholebody.npz` files from the student's CLI still load
(schema "0": no boxes, no video hash), but the precomputed source refuses them because they
cannot be tied to a video.

## Steps

1. **Target swimmer.** The detector's people are reduced to one target per frame by tracking
   (`select_target`): the box overlapping the previous target, else the nearest, else (first
   frame) the largest area x confidence. The student's `BoxTracker` carries the last box up to
   0.5 s through detector misses and drops it when RTMW finds no body in it.
2. **Other people.** `find_segments` splits the clip wherever the target box jumps: no overlap
   with the previous box and the centre moved more than `0.5 + 1.5 x seconds` box diagonals.
   The person followed for the most frames is the target. Another segment is accepted only if
   it is consistent with the accepted segment next to it; the rest is rejected
   (`OTHER_SWIMMER`) before cleanup runs, so nothing is interpolated or smoothed across a
   change of swimmer.
3. **Cleanup** (existing code): drop points scored under 3.0; drop frames whose body line is
   flipped or whose trunk length is far off; swap left/right back; drop anatomically impossible
   points; drop one-frame spikes; fill gaps up to 0.2 s by straight-line interpolation with
   confidence x 0.3; smooth with a confidence-weighted local line fit (sigma 0.04 s).
4. **Labels.** Observed (kept), interpolated (filled, low confidence), rejected (the model gave
   a point and it was thrown out), missing (the model gave nothing). Longer gaps stay missing.
5. **Quality report and grade** (below), then stroke cycles from the cleaned pose.

## Thresholds

All are engineering baselines. They were chosen by reasoning and by the student's work on a
sample clip, not fitted to labelled data, because no real clip with per-frame joint labels
at video rate is available to us (SWIM-360 labels every 10th frame).

| Threshold | Value | Reasoning | Status |
|---|---|---|---|
| Minimum RTMW score | 3.0 | Student's observation: points under about 3 were visibly wrong on their clip; clear frames score 4 to 8 | Kept; to be re-checked on the Phase 1 real clips |
| Gap interpolation | 0.2 s | A hand moves up to about 10 trunk lengths per second, so a straight line across more than about 0.2 s can be far from the real path; 0.2 s is 5 frames at 25 fps | Kept; supported by the check below on one real clip |
| Filled confidence | x 0.3 | Filled points must never count as reliable (cycles need confidence of 0.3 or more from real points) | Kept |
| Smoothing | sigma 0.04 s | About one frame: removes jitter without rounding off the catch or entry | Kept |
| Box carry | 0.5 s | Student's value for splash-hidden frames | Kept |
| Identity jump | 0.5 + 1.5/s diagonals | A sprinter covers about 1.2 body lengths per second; the rest is slack for a panning camera and changing box shape | New in Phase 1; unit-tested on synthetic switches only |

### Checking the gap limit (done on real pose data, 2026-11-15)

On the real pose of the primary test clip (Front Crawl Underwater, 328 frames, 25 fps, a slow
swimmer with a 2.5 s arm cycle), points the model placed confidently were hidden for 1 to 12
frames, filled by straight-line interpolation, and compared with the hidden positions. Error is
the largest miss inside the gap, in trunk lengths (trunk = 350 px in this clip).

| Gap | Wrists median / p90 | Elbows median / p90 | Shoulders and hips median / p90 | Ankles median / p90 |
|---|---|---|---|---|
| 0.04 s | 0.007 / 0.07 | 0.008 / 0.06 | 0.006 / 0.01 | 0.011 / 0.02 |
| 0.12 s | 0.024 / 0.21 | 0.026 / 0.18 | 0.018 / 0.04 | 0.037 / 0.08 |
| 0.20 s | 0.046 / 0.32 | 0.045 / 0.30 | 0.032 / 0.07 | 0.073 / 0.15 |
| 0.32 s | 0.080 / 0.45 | 0.082 / 0.43 | 0.053 / 0.11 | 0.129 / 0.26 |
| 0.48 s | 0.133 / 0.58 | 0.136 / 0.65 | 0.084 / 0.16 | 0.205 / 0.37 |

Reading: up to 0.2 s the typical error stays under 5% of a trunk length, but the worst tenth of
arm gaps is already off by about 0.3 trunk lengths, and it grows quickly beyond that. So 0.2 s
is kept as the upper limit and filled points keep their reduced confidence. This compares
interpolation with the model's own output, not with the truth, and comes from one slow clip;
faster swimmers will do worse at the same gap length.

## Quality report

Percentages are over the 12 limb joints (shoulders, elbows, wrists, hips, knees, ankles).
A frame has a **valid pose** when at least 3 of the 4 shoulder and hip points and at least 8
of the 12 limb joints are usable (observed or interpolated).

Grade, from the data only:

- **insufficient** if under 40% of frames have a valid pose, or under 2 s of valid pose in total.
  Stroke numbers are then withheld.
- **good** if all hold: at least 80% valid frames; shoulders and hips usable at least 80%;
  elbows and wrists at least 60%; at most 5% of frames followed someone else; at least 4
  reliable stroke cycles.
- **limited** otherwise. Numbers are shown with the reasons.

The filming angle never changes the grade. Known limits of a view or stroke are listed
separately (`filming_limitations`).

## Stroke numbers

- A stroke cycle is one full turn of one arm, found from the arm's angle around the shoulder
  (`metrics/cycles.py`). A cycle is "reliable" when enough of its frames have a trusted
  shoulder and wrist and its length is plausible for the clip.
- Stroke rate and time per cycle use the reliable cycles only.
- A stroke **count** is reported only when every cycle found in the clip is reliable. If any
  were unclear, the count is withheld with the reason, because the reliable ones alone would
  undercount (seen on the sprint test clip: 8 reliable of about 17 real arm cycles).

## Limits

- Everything depends on RTMW being right when it is confident. On SWIM-360 underwater frames
  elbows and wrists were within tolerance only 59% of the time even with a perfect box.
- One 2D camera: the far arm and leg are often hidden; body rotation is not measurable from
  the side.
- Stroke cycles are found from the arm turning around the shoulder: validated by unit tests
  on a synthetic swimmer, checked on real video only as far as Phase 1 reports. Breaststroke
  is not supported.
- Identity handling follows the box, not appearance. Two swimmers who overlap in the picture
  can still be confused.

## Pose model weights used for the Phase 1 real-video check

The student's `rtmw_x_stock.onnx` (in their Google Drive) is their own ONNX export of the
official OpenMMLab checkpoint `rtmw-x_simcc-cocktail14_pt-ucoco_270e-384x288-f840f204_20231122.pth`.
OpenMMLab publishes no ONNX file for that checkpoint. For the Phase 1 validation the same
public checkpoint was downloaded in Colab (its SHA-256 starts with `f840f204`, as the file name
promises) and exported with the same wrapper and settings as the student's notebook (head
output as `simcc_x` / `simcc_y`, opset 17).

- The export is exactly as large as the student's file (368,740,410 bytes). The SHA-256 differs
  (`5ff227bf...` here, `487a1ebe...` for the student's), which is expected for exports made at
  different times with different library versions. The two files were not compared output by
  output, so equivalence is very likely but not proven.
- Raw score levels match what the student documented (median 7.4 on the pilot frames, all
  body points above the 3.0 cut-off).
- The official `onnx_sdk` RTMW-x 384x288 ONNX (cocktail13, an earlier model generation) loads
  and has the same input and output shapes, but its scores are on a different scale (median
  0.79 on the same frames, none above 3.0). With the current cut-offs every point would be
  rejected, so it is not a drop-in replacement.
