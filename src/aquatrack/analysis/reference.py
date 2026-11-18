"""Strong-swimmer reference hints: the swimmer's value next to strong swimmers filmed the
same way (freestyle, underwater side view), measured by this same pipeline.

Owner's decision (2026-11-18): the swimmer is still compared with themselves for findings,
priorities and history. These hints are a separate, labelled extra so a swimmer with no
history gets some orientation from their first video. They never create a finding, never
rank anything, and are never worded as a fault: three swimmers are not a norm, and good
swimmers differ (a 50 m sprinter pulls with a straighter arm than a distance swimmer).

Values: docs/REFERENCE_SWIMMERS.md (clips, how they were measured, limits). Bump
REFERENCE_VERSION on any change to the values, groups or tolerances.
"""

from aquatrack.contracts import (
    AnalysisResult,
    MetricStatus,
    ReferenceComparison,
    ReferenceSwimmer,
)

REFERENCE_VERSION = "2026.11-1"
SPRINT_MAX_M = 100  # a swim of this distance or shorter is set against the sprinter

_W = ("Florian Wellbrock", "distance", "Olympic distance and open-water champion, easy swim")
_E = ("Effortless Swimming coach", "distance", "good adult swimmer, not an elite racer")
_K = ("Andrii Khloptsov", "sprint", "elite sprinter, 50 m freestyle race pace")

# metric -> (tolerance, [(swimmer, value, cycles)]). Tolerance: differences smaller than this
# are not told apart (angles: the 90th-percentile forearm direction error on SWIM-360;
# trunk-length metrics: the pose noise used by the interpretation rules).
VALUES: dict[str, tuple[float, list[tuple[tuple[str, str, str], float, int]]]] = {
    "catch_forearm_angle": (7.0, [(_W, 0.0, 13), (_E, 0.6, 10), (_K, 50.4, 9)]),
    "elbow_angle_min": (7.0, [(_W, 125.0, 14), (_E, 118.8, 10), (_K, 118.1, 9)]),
    "pull_depth": (0.05, [(_W, 0.71, 14), (_E, 0.85, 10), (_K, 0.91, 9)]),
    "head_height": (0.05, [(_W, -0.03, 14), (_E, -0.04, 10), (_K, -0.02, 9)]),
}

LIMITS = [
    "Three swimmers filmed the same way, measured by AquaTrack: an orientation, not a norm.",
    "Good swimmers differ from each other; a value outside this range says only where it sits.",
    "The reference swimmers are adult men; this may not carry over to young or beginner swimmers.",
]


def _groups(result: AnalysisResult) -> list[str]:
    """Which reference groups to set the clip against, from the distance the swimmer entered.
    Unknown distance: each group separately, never one merged range (a sprinter's and a
    distance swimmer's values can be far apart, and a merged range would hide that)."""
    text = result.session.distance.lower().replace("m", " ").split()
    try:
        metres = float(text[0]) if text else None
    except ValueError:
        metres = None
    if metres is None:
        return ["distance", "sprint"]
    return ["sprint" if metres <= SPRINT_MAX_M else "distance"]


def compare(result: AnalysisResult) -> list[ReferenceComparison]:
    """Reference hints for the metrics that were measured in this clip. Only freestyle in an
    underwater view: the references were filmed that way."""
    stroke, camera = result.session.stroke.lower(), result.session.camera.lower()
    if (stroke and stroke != "freestyle") or (camera and not camera.startswith("underwater")):
        return []
    groups = _groups(result)
    out = []
    for m in result.metrics or []:
        if m.key not in VALUES or m.value is None or m.status is MetricStatus.UNAVAILABLE:
            continue
        tolerance, rows = VALUES[m.key]
        for group in groups:
            swimmers = [
                ReferenceSwimmer(name=s[0], group=s[1], note=s[2], value=v, n_cycles=n)
                for s, v, n in rows
                if s[1] == group
            ]
            low, high = min(x.value for x in swimmers), max(x.value for x in swimmers)
            if m.value < low - tolerance:
                position = "below"
            elif m.value > high + tolerance:
                position = "above"
            else:
                position = "within"
            out.append(
                ReferenceComparison(
                    metric_key=m.key,
                    label=m.label,
                    unit=m.unit,
                    value=m.value,
                    metric_status=m.status.value,
                    group=group,
                    low=low,
                    high=high,
                    tolerance=tolerance,
                    position=position,
                    swimmers=swimmers,
                    limitations=[*LIMITS, *m.limitations],
                )
            )
    return out
