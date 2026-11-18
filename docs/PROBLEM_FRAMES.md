# Problem frames

Still frames from the swimmer's own video that show the feedback's priorities, on the result
page (`/history/[id]`). Code: `src/aquatrack/analysis/problem_frames.py`, contract
`ProblemFrames` in `src/aquatrack/contracts.py`, parser `frontend/app/lib/problemFrames.ts`,
stage `frontend/app/components/ProblemFrameStage.tsx`. Tests: `tests/test_problem_frames.py`,
`frontend/tests/problemFrames.test.ts`.

## What may be shown

- Only feedback items with category `priority` (ranked). An unranked focus is not a "fix" and
  gets no frames. No priority: no frames, `empty_reason = "no_issue"`.
- Only moments named by that priority's own evidence samples. A rule must be listed in
  `FRAME_RULES` to have frames at all; any other priority gives `no_frame_rule`.
  - `timing.uneven_rhythm`: the off-rhythm cycles (`cycle_duration` samples). Each cycle starts
    at the timing arm's mid-pull, so the arrow points at that arm's wrist, labelled with the
    measured cycle time and the clip's own median ("Longer cycle: 2.62 s (usual 2.56)").
  - `history.rhythm_less_steady`: its evidence is one number with no cycles, so no frames.
- At most 5 frames, at most one per cycle, round-robin over the priorities with the main one
  first, and within a priority the cycles furthest from the swimmer's own median first.

## When a frame is trusted

For the arm the evidence was measured on, all of:

1. It is the arm nearer the camera (`coverage.camera_side`); the far arm is hidden.
2. The frame is `SUPPORTED` for that arm (`usability.ArmFrame`): the model's own shoulder,
   elbow and wrist inside an underwater pull that was followed, with believable segment
   lengths. Recomputed from the stored raw pose with the same, model-free steps.
3. Shoulder, elbow and wrist are `OBSERVED` (not filled in), confidence at least 0.5, and at
   least 2% of the picture away from its edges.
4. Not blurry: variance of the Laplacian around the arm at least half the median of the
   clip's candidate frames.

If the evidence frame fails, up to 2 frames either side inside the same cycle may stand in;
the stored timestamp is the frame actually shown. Nothing passes: `no_trusted_frame`.

## Storage and lifecycle

The worker runs this right after feedback, while the video and raw pose are still on disk.
Firestore `videos/{id}/frames/{feedbackId}` (owner read, backend write), JPEGs (max 1280 px
wide) in Storage `analysis/{uid}/{id}/{analysisId}/frames/{feedbackId}/{n}.jpg`; both are
removed with the video. Arrow points are 0-1 of the original (unmirrored) picture.
`POST /videos/{id}/interpret` builds new feedback without the video, so it has no frames; the
page then shows the video with a note.

## Limits

- Placement checked by eye on one real clip (5 frames) with a synthetic priority; no real
  clip has produced a priority yet.
- Sharpness is relative to the clip's own candidates, not an absolute standard.
