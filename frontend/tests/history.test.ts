// Tests for comparison and progress data preparation. Fixtures are SYNTHETIC sessions made
// by the Python engine from the synthetic swimmer with edited values: they test the logic
// and are not anyone's progress. Run: npm test
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  chartPoints,
  parseComparison,
  parseProgress,
  recordViews,
  stateLabel,
  stateTone,
} from "../app/lib/history.ts";

const load = (name: string) =>
  JSON.parse(
    readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8"),
  );

test("a compatible pair gives per-metric changes in neutral words", () => {
  const c = parseComparison(load("comparison_compatible"));
  assert.ok(c && c.comparable);
  const by = Object.fromEntries(c.metrics.map((m) => [m.metricKey, m]));
  assert.equal(by.leg_line_angle.state, "increased");
  assert.equal(by.leg_line_angle.change, 10);
  assert.ok((by.leg_line_angle.threshold ?? 0) >= 4);
  assert.equal(by.stroke_rate.state, "no_clear_change");
  assert.equal(by.pull_depth.state, "not_comparable");
  assert.equal(by.pull_depth.change, null);
  assert.ok(by.pull_depth.reasons.length > 0);
  const words = JSON.stringify([
    c.summary,
    Object.values(stateLabel),
  ]).toLowerCase();
  assert.ok(!/improv|better|worse|good|bad/.test(words));
  assert.equal(stateTone.increased, stateTone.decreased); // a rise is not shown as good
});

test("a different effort is not compared, and no change is shown for any metric", () => {
  const c = parseComparison(load("comparison_different_effort"));
  assert.ok(c);
  assert.equal(c.comparable, false);
  assert.ok(c.sessionReasons[0].includes("different effort"));
  assert.ok(
    c.metrics.every(
      (m) =>
        m.state === "not_comparable" &&
        m.change === null &&
        m.threshold === null,
    ),
  );
});

test("a document can't turn a non-comparable metric into a change", () => {
  const doc = load("comparison_different_effort");
  doc.metrics[0].change = 5;
  doc.metrics[0].threshold = 1;
  doc.comparable = true;
  const c = parseComparison(doc);
  assert.ok(c);
  assert.equal(c.metrics[0].change, null);
  assert.equal(c.comparable, false);
  assert.equal(parseComparison({ comparison_version: "2.0" }), null);
});

test("progress keeps incompatible sessions on separate lines and draws only real points", () => {
  const p = parseProgress(load("progress_synthetic_series"));
  assert.ok(p);
  assert.equal(p.baseline, false);
  assert.deepEqual(
    p.series.map((s) => s.sessions.length),
    [3, 1],
  );
  const leg = p.series[0].metrics.find((m) => m.metricKey === "leg_line_angle");
  assert.ok(leg);
  assert.deepEqual(
    leg.points.map((x) => x.videoId),
    ["a", "b", "c"],
  );
  assert.equal(leg.overall?.state, "increased");
  const sprintIds = new Set(p.series[1].sessions.map((s) => s.videoId));
  assert.ok(
    p.series[0].metrics.every((m) =>
      m.points.every((x) => !sprintIds.has(x.videoId)),
    ),
  );
  assert.deepEqual(
    p.notIncluded.map((n) => n.session.videoId),
    ["weak"],
  );
  assert.ok(p.notIncluded[0].reasons[0].includes("could not be followed"));
  assert.ok(p.followups.length > 0 && p.openCheckpoints.length > 0);
});

test("points that don't belong to the series, and fake baselines, are dropped", () => {
  const doc = load("progress_synthetic_series");
  doc.progress.series[0].metrics[0].points.push({
    video_id: "invented",
    recorded_at: "2026-12-01",
    value: 99,
  });
  doc.progress.baseline = true;
  const p = parseProgress(doc);
  assert.ok(p);
  assert.ok(
    p.series[0].metrics[0].points.every((x) => x.videoId !== "invented"),
  );
  assert.equal(p.baseline, false);
});

test("one video is a baseline, and no videos shows nothing at all", () => {
  const one = parseProgress(load("progress_single_baseline"));
  assert.ok(one && one.baseline);
  assert.ok(
    one.series[0].metrics.every(
      (m) => m.points.length === 1 && m.overall === null,
    ),
  );
  assert.ok(one.note.includes("baseline"));
  assert.ok(one.openCheckpoints.length > 0 && one.followups.length === 0);
  const none = parseProgress(load("progress_empty"));
  assert.ok(none && none.baseline);
  assert.deepEqual(
    [none.series, none.history, none.openCheckpoints],
    [[], [], []],
  );
  assert.equal(none.analyzed, 0);
});

test("chart points stay inside the box, oldest first, and one point is centred", () => {
  const pts = chartPoints([8, 10, 9], 280, 64);
  assert.deepEqual(
    pts.map((x) => x.x),
    [12, 140, 268],
  );
  assert.ok(pts.every((x) => x.y >= 12 && x.y <= 52));
  assert.ok(pts[1].y < pts[0].y); // a larger value sits higher
  assert.deepEqual(chartPoints([5], 280, 64), [{ x: 140, y: 32 }]);
  assert.deepEqual(
    chartPoints([4, 4], 280, 64).map((x) => x.y),
    [32, 32],
  );
  assert.deepEqual(chartPoints([], 280, 64), []);
});

test("self-reported times: a target only applies to the same event and pool", () => {
  const pbs = [
    { event: "50 Free", pool: "25 m", seconds: 31.2 },
    { event: "100 Free", pool: "25 m", seconds: 70.5 },
  ];
  const views = recordViews(pbs, {
    event: "50 Free",
    pool: "25 m",
    seconds: 30,
  });
  assert.deepEqual(views[0], {
    event: "50 Free",
    pool: "25 m",
    best: 31.2,
    target: 30,
    gap: 1.2,
  });
  assert.equal(views[1].target, null);
  assert.equal(
    recordViews(pbs, { event: "50 Free", pool: "50 m", seconds: 30 })[0].target,
    null,
  );
  assert.deepEqual(recordViews([], null), []);
});
