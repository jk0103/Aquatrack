# History, comparison, progress and deletion (comparison 1.0)

Code: `src/aquatrack/analysis/comparison.py`, `src/aquatrack/api/jobs.py`
(`compare_videos`, `progress_for`, `delete_video`), `src/aquatrack/api/store.py`
(`delete_video_data`). Screens: History, Compare, Progress, video detail.

## 1. What was real, what was example, what is new

| Area | Before Phase 5 | Now |
| --- | --- | --- |
| History list | Real uploads, stroke filter; example analyses below (labelled) | Same, plus a status filter and choosing two analysed videos to compare |
| Progress page | Example data only | Real progress from stored analyses on top; the example time chart stays below, labelled |
| Comparing two videos | Only inside the interpretation (whole session or nothing) | Its own engine and screen, decided per metric |
| Checkpoints | Listed per video | Stored with their baseline and origin; the next video reports on them |
| Deleting a video | Not possible | Backend deletion with ownership check, safe to repeat |

## 2. Comparison

Computed from two stored `AnalysisResult`s each time it is asked for. Nothing is stored, no pose
inference runs, and the analyses compared are named in the result.

**Ruled out as a whole** (every metric "not comparable", with the reason): a different stroke,
filming angle or distance entry; a clearly different effort (stroke rates more than 20% apart);
a clip in which the swimmer could not be followed; an analysis from before metrics existed.

**Decided per metric** otherwise:

| Check | Outcome |
| --- | --- |
| Arm metrics (pull depth, elbow, pull path) | not comparable: for information only |
| The metric's definition changed between the two analysis versions | not comparable. Timing metrics are defined the same since 1.1; body-position metrics since 1.2. There is no conversion, and old values are never recomputed |
| Body-position metric and the camera view changed in either clip | not comparable |
| The metric is limited or unavailable in either clip | insufficient evidence, with each clip's reason |
| Both passed their checks | increased / decreased / no clearly measurable change |

A change counts only above a threshold: for cycle time 2 video frames, for body and leg line
4 degrees, for head position 0.10 trunk lengths, and in every case at least the average spread
(middle half) of the two values; for rhythm variation, twice the combined sampling error plus
the timing resolution. Reported per metric: previous, current, difference, percentage (stroke
rate and cycle time only), threshold, both reliability states, cycle counts, reasons, limits.

The words are neutral. "Increased" and "decreased" say which way a number moved. Nothing says
better or worse, and both directions are shown in the same colour.

## 3. Progress

`GET /progress` groups the swimmer's analysed sessions into **series**: a session joins the
first series whose first session it may be compared with as a whole, otherwise it starts its
own. Within a series a metric gets a point only for sessions where it passed its checks, is
defined the same way as in the series' first session, and (for body position) the view was
steady. Nothing is interpolated. A sprint and an easy swim never share a line.

Also returned: sessions left out and why; limitations that repeat (camera view, short clips,
untrackable clips), reported as filming issues; what each analysis found (from the stored
interpretations, not recomputed); the newest video's open checkpoints and its follow-ups.

One analysed video, or no two comparable ones, is a **baseline**: values are shown, no trend.

Times on the Progress page come from the profile and are labelled "Entered by you". A target
is shown against a personal best only for the same event and pool length. They are never
derived from video and never linked to a technique measurement. The swimmer's own note is shown
as their own words; it is not analysed and not sent anywhere.

## 4. Checkpoints across sessions

Each checkpoint stores why it was made, the values measured in its video (`baseline`), the
video and analysis it came from and when. When a later video is interpreted, the checkpoints of
the swimmer's previous analysed video are followed up and stored with the new video's feedback:

| State | Meaning |
| --- | --- |
| Not yet evaluated | no later video yet (shown on Progress for the newest video) |
| Comparable measurement available | a filming requirement was met (longer clip, steady side view) |
| Measurable change observed | a matching metric moved by more than its threshold |
| No clear measurable change | matching metrics differ by less than their thresholds |
| Cannot evaluate from this video | not comparable, with the reason |

A change is never called an improvement. Earlier feedback documents are not modified, so the
checkpoint history stays as it was written.

## 5. History in interpretation (rules 2026.11-2)

- If the uneven-rhythm rule triggers and the same rule also triggers on earlier compatible
  swims (re-run on their stored analyses), the finding records the recurrences and they count
  toward "Seen across swims". A recurring pattern can therefore become a priority without a
  goal. It is still worded as worth a look.
- A value that stays the same across three or more compatible swims is reported as steady. It
  never becomes an issue, however unusual the value.
- Nothing else changed: no threshold was lowered and no pending rule was activated.

## 6. Deletion

`DELETE /videos/{id}` (login required):

1. In one transaction: check the caller owns the video, set its status to `deleting`. From then
   on no analysis can be requested, and a running analysis stores nothing.
2. Delete the analysis artifacts in Storage (`analysis/{uid}/{id}/`), the uploaded video file,
   the `feedback`, `interpretations` and `analyses` documents, and last the video record.
3. If a step fails, the record stays with status `deleting`; the API answers 503 without any
   path, and the same request finishes the job. A video that is already gone is reported as
   deleted. Someone else's video looks like a missing one (404).

The security rules still forbid any client-side delete of videos, results or artifacts.
Comparisons and progress are computed from what exists, so a deleted video simply disappears
from them. Stored interpretations and feedback of *other* videos may still mention the deleted
video's id (as an earlier session or a checkpoint source); those are opaque ids, not content.

**Before production** (not done): a durable deletion queue with retries and reconciliation for
records left in `deleting`; account-level deletion; backups and their retention; logs that may
hold ids; a written retention policy and the legal review that goes with it; consent handling
for videos showing minors; deletion from any CDN or cache; an audit trail.

## 7. Limits

- Comparison thresholds are engineering choices. No real swimmer has two comparable sessions
  in the test data: the two real clips are different efforts and are correctly not compared.
  All comparison, progress and follow-up behaviour was exercised on labelled synthetic sessions.
- "Similar effort" is judged by stroke rate only. The distance is what the swimmer entered.
- Series are anchored on their first session; a slow drift in effort across many sessions is
  not detected.
- A change in a number is not shown to relate to swimming faster or better.
