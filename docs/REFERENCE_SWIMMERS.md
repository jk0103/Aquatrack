# Strong-swimmer reference hints (reference 2026.11-1)

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
2026-11-18 by this pipeline (analysis schema 1.2) from RTMW-x pose saved locally; no new model
run was needed for the numbers.

| Swimmer | Group | Clip | Reliable cycles |
| --- | --- | --- | --- |
| Florian Wellbrock | distance | side view through a pool window, easy freestyle, about 30 s | 14 |
| Effortless Swimming coach | distance | underwater side view, steady freestyle, about 30 s (good adult swimmer, not an elite racer) | 10 |
| Andrii Khloptsov | sprint | underwater side view following the swimmer, 50 m race pace | 9 |

| Metric | Wellbrock | Effortless | Khloptsov |
| --- | --- | --- | --- |
| catch_forearm_angle (deg) | 0.0 | 0.6 | 50.4 |
| elbow_angle_min (deg) | 125.0 | 118.8 | 118.1 |
| pull_depth (trunk lengths) | 0.71 | 0.85 | 0.91 |
| head_height (trunk lengths) | -0.03 | -0.04 | -0.02 |

Left out: stroke rate and cycle time (depend on pace, which is not measured), body and leg line
(the level reference wandered in two of the clips), rhythm (the Wellbrock clip is cut together
from several passes). Clips tried and not usable: Phelps (cuts and changing angles), McEvoy and
Park Tae-hwan (filmed head-on).

## Limits

- Three adult men. This is an orientation, not a norm, and may not carry over to young or
  beginner swimmers.
- Good technique differs between swimmers and events: the sprinter's catch angle (50 degrees,
  a straighter arm) is far from the distance swimmers' (0 to 1 degrees).
- Not validated against any outcome; nothing here says that moving toward the range makes
  anyone faster.
