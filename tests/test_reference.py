"""Strong-swimmer reference hints. Synthetic swimmer only; nothing here shows the hints are
useful to real swimmers."""

import pytest
from test_interpretation import EVEN, result

from aquatrack.analysis import reference
from aquatrack.analysis.explain import JUDGING
from aquatrack.analysis.feedback import build_feedback
from aquatrack.analysis.interpretation import interpret
from aquatrack.contracts import MetricStatus


def metric(r, key):
    return next(m for m in r.metrics if m.key == key)


def hints(r):
    return {h.metric_key: h for h in reference.compare(r) if h.group == "distance"}


def test_hints_only_for_measured_metrics_with_reference_values():
    r = result(EVEN)
    keys = set(hints(r))
    assert keys <= set(reference.VALUES)
    for k in keys:
        assert metric(r, k).status is not MetricStatus.UNAVAILABLE


@pytest.mark.parametrize(
    "distance, groups",
    [
        ("50 m", {"sprint"}),
        ("100m", {"sprint"}),
        ("400 m", {"distance"}),
        ("", {"sprint", "distance"}),
    ],
)
def test_reference_group_follows_the_distance_the_swimmer_entered(distance, groups):
    r = result(EVEN, distance=distance)
    out = reference.compare(r)
    assert out and {h.group for h in out} == groups
    for h in out:  # never one range merged across groups
        assert all(s.group == h.group for s in h.swimmers)


def test_position_uses_the_range_widened_by_the_tolerance():
    r = result(EVEN, distance="400 m")
    m = metric(r, "pull_depth")
    m.status = MetricStatus.RELIABLE
    low = min(v for s, v, _ in reference.VALUES["pull_depth"][1] if s[1] == "distance")
    tol = reference.VALUES["pull_depth"][0]
    m.value = low - tol / 2
    assert hints(r)["pull_depth"].position == "within"
    m.value = low - tol * 2
    assert hints(r)["pull_depth"].position == "below"


def test_no_hints_for_other_strokes_or_views():
    assert reference.compare(result(EVEN, stroke="Backstroke")) == []
    assert reference.compare(result(EVEN, camera="Above water")) == []


def test_hints_never_become_findings_and_are_worded_neutrally():
    r = result(EVEN, distance="400 m")
    m = metric(r, "pull_depth")
    m.status, m.value = MetricStatus.RELIABLE, 0.2  # far outside the reference range
    i = interpret(r, "v", "a1")
    assert any(h.metric_key == "pull_depth" for h in i.references)
    assert not any("pull_depth" in f.metric_keys for f in i.issue_candidates)
    assert i.reference_version == reference.REFERENCE_VERSION
    items = [x for x in build_feedback(i, "i1").items if x.category == "reference"]
    assert items and all(x.rank is None and x.confidence == "for_information" for x in items)
    for x in items:
        assert not JUDGING.search(x.title + " " + x.body), x.body
