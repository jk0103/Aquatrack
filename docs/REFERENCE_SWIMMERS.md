# Strong-swimmer reference hints (reference 2026.11-2)

Owner's decision, 2026-11-18: findings, priorities and history still compare the swimmer only
with themselves. In addition, a few measurements are shown next to the same measurements of
strong swimmers filmed the same way, so a swimmer with no earlier videos gets some orientation
from the first upload. Code: `src/aquatrack/analysis/reference.py` (values, groups,
tolerances), `interpretation.py` (`Interpretation.references`), `feedback.py` (category
`reference`), `frontend/app/components/FeedbackPanel.tsx` ("Compared with strong swimmers").

## Rules

- A hint is never a finding: it never creates an issue candidate or a priority, is never ranked,
  never feeds training plans, and is worded as where a value sits ("in the same range as",
  "below / above the range of"), never as better, worse or a fault. The explainer rejects
  judging words for this category.
- Only metrics that were measured in the clip (reliable or limited, with the metric's own
  status shown); never for unavailable metrics. Only freestyle in an underwater view.
- Group: the swim distance the swimmer entered. 100 m or less is set against the sprinter, more
  against the distance swimmers. With no distance, one hint per group, never one merged range
  (the sprinter's catch angle is 50 degrees from the distance swimmers').
- Tolerance: a value within the reference range widened by the tolerance counts as "in the same
  range". Angles 7 degrees (90th percentile forearm direction error on SWIM-360, see
  `docs/BIOMECHANICS_METRICS.md`), trunk-length metrics 0.05 (the pose noise used by the
  interpretation rules).

## Reference swimmers

Public clips downloaded by the owner for tuning only. The videos are not in the repository and
are never shown in the app; only the numbers measured from them are used. Measured on
2026-11-18 by this pipeline (analysis schema 1.2) from RTMW-x pose saved locally. The saved
pose itself came from local model runs on 2026-11-11; only the re-measuring on 2026-11-18
needed no new model run.

Version 2026.11-2 (2026-11-27) changed no value, group or tolerance. It removed descriptions
of the swimmers and clips that had been written as facts but were guesses: the pace swum
("easy", "steady", "race pace"), the level of two of the swimmers, "adult men", and the claim
that one clip is cut together from several passes. None of these was measured or checked
against a source.

| Swimmer | Group | Clip | Reliable cycles |
| --- | --- | --- | --- |
| Florian Wellbrock | distance | side view, freestyle, about 30 s; pace not verified | 14 |
| Effortless Swimming coach | distance | underwater side view, freestyle, about 30 s; level and pace not verified | 10 |
| Andrii Khloptsov | sprint | underwater side view following the swimmer; clip titled 50 m freestyle, level and pace not verified | 9 |

| Metric | Wellbrock | Effortless | Khloptsov |
| --- | --- | --- | --- |
| catch_forearm_angle (deg) | 0.0 | 0.6 | 50.4 |
| elbow_angle_min (deg) | 125.0 | 118.8 | 118.1 |
| pull_depth (trunk lengths) | 0.71 | 0.85 | 0.91 |
| head_height (trunk lengths) | -0.03 | -0.04 | -0.02 |

Left out: stroke rate and cycle time (depend on pace, which is not measured), body and leg line
(the level reference wandered in two of the clips), rhythm (not established that every clip is
one continuous swim, which a rhythm value needs). Clips tried and not usable: Phelps (cuts and changing angles), McEvoy and
Park Tae-hwan (filmed head-on).

## Limits

- Three swimmers whose age, level and pace in the clip were not verified. The groups
  ("distance", "sprint") come from general knowledge of the swimmer or the clip's title, not
  from a checked source or a measured pace. Calling them "strong swimmers" is likewise not
  verified for two of the three. This is an orientation, not a norm, and may not carry over to young or
  beginner swimmers.
- The values differ between the clips: the sprint clip's catch angle (50 degrees) is far from
  the other two (0 to 1 degrees). Three clips cannot show whether that is the event, the
  swimmer or the pace.
- Not validated against any outcome; nothing here says that moving toward the range makes
  anyone faster.
