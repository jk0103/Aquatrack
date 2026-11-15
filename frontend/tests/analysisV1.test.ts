// Parser tests for analysis results. Fixtures are synthetic-swimmer results written by the
// Python pipeline (no real video). Run: npm test
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { formatMetric, parseAnalysisV1 } from "../app/lib/analysisV1.ts";

const load = (name: string) =>
  JSON.parse(
    readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8"),
  );

test("a 1.1 result gives metrics with their own status and the four coverage levels", () => {
  const a = parseAnalysisV1(load("analysis_1_1"));
  assert.ok(a && a.coverage);
  assert.equal(a.schemaVersion, "1.1");
  const byKey = Object.fromEntries(a.metrics.map((m) => [m.key, m]));
  assert.equal(byKey.stroke_rate.status, "reliable");
  assert.equal(byKey.stroke_rate.value, 50);
  assert.equal(byKey.elbow_angle_min.status, "limited");
  assert.ok(byKey.elbow_angle_min.reason.includes("not the true joint angle"));
  assert.equal(byKey.cycle_time_change.status, "unavailable");
  assert.equal(byKey.cycle_time_change.value, null);
  assert.ok(
    byKey.leg_line_angle.samples.every((s) => s.t >= 0 && s.start !== null),
  );
  assert.ok(a.metrics.every((m) => m.description && m.limitations.length > 0));
  assert.equal(a.coverage.cameraSide.arm, "right");
  assert.equal(a.coverage.cycles.status, "complete");
  assert.equal(
    a.coverage.metricsReliable +
      a.coverage.metricsLimited +
      a.coverage.metricsUnavailable,
    a.metrics.length,
  );
  assert.equal(a.coverage.arms.length, 2);
});

test("a Phase 1 (1.0) result still parses and simply has no metrics", () => {
  const a = parseAnalysisV1(load("analysis_1_0"));
  assert.ok(a);
  assert.equal(a.schemaVersion, "1.0");
  assert.deepEqual(a.metrics, []);
  assert.equal(a.coverage, null);
  assert.deepEqual(
    a.measurements.map((m) => m.key),
    ["stroke_rate", "cycle_duration"],
  );
  assert.ok(a.stroke.cycles.every((c) => c.kind === ""));
});

test("an insufficient clip shows no numbers at all", () => {
  const a = parseAnalysisV1(load("analysis_1_1_insufficient"));
  assert.ok(a && a.coverage);
  assert.equal(a.quality.grade, "insufficient");
  assert.ok(a.metrics.length > 0);
  assert.ok(
    a.metrics.every(
      (m) => m.status === "unavailable" && m.value === null && m.reason,
    ),
  );
  assert.equal(a.coverage.cycles.status, "none");
});

test("a metric that claims a status but has no number is never shown as measured", () => {
  const doc = load("analysis_1_1");
  doc.metrics[0].value = null;
  doc.metrics[1].status = "certain"; // unknown status: dropped
  const a = parseAnalysisV1(doc);
  assert.ok(a);
  assert.equal(a.metrics[0].status, "unavailable");
  assert.equal(a.metrics.length, doc.metrics.length - 1);
});

test("unknown or half-written documents are rejected, not shown", () => {
  assert.equal(
    parseAnalysisV1({ schema_version: "2.0", quality: {}, stroke: {} }),
    null,
  );
  assert.equal(parseAnalysisV1({ schema_version: "1.1" }), null);
  assert.equal(parseAnalysisV1(null), null);
});

test("numbers are formatted per unit and never as minus zero", () => {
  assert.equal(formatMetric(-0.04, "deg"), "0.0");
  assert.equal(formatMetric(53.12, "cycles/min"), "53.1");
  assert.equal(formatMetric(0.737, "trunk lengths"), "0.74");
  assert.equal(formatMetric(8, "cycles"), "8");
});

test("a 1.2 result has five exclusive arm classes that add up to 100", () => {
  const a = parseAnalysisV1(load("analysis_1_2"));
  assert.ok(a && a.coverage);
  assert.equal(a.schemaVersion, "1.2");
  for (const arm of a.coverage.arms) {
    const parts = [
      arm.supportedPct,
      arm.interpolatedPct,
      arm.modelOnlyPct,
      arm.rejectedPct,
      arm.missingPct,
    ];
    assert.ok(parts.every((x) => x !== null));
    const total = parts.reduce((sum: number, x) => sum + (x ?? 0), 0);
    assert.ok(Math.abs(total - 100) < 0.11, `classes add up to ${total}`);
    assert.ok((arm.modelOnlyInFrontPct ?? 0) <= (arm.modelOnlyPct ?? 0) + 0.11);
  }
  assert.ok(a.coverage.arms.some((arm) => (arm.interpolatedPct ?? 0) > 0));
  assert.equal(a.coverage.view?.status, "steady");
  assert.ok(a.metrics.every((m) => m.excludedCycles === 0));
});

test("a 1.1 result (before the exclusive classes) still parses, with those classes absent", () => {
  const a = parseAnalysisV1(load("analysis_1_1"));
  assert.ok(a && a.coverage);
  assert.equal(a.coverage.view, null);
  assert.ok(
    a.coverage.arms.every(
      (arm) => arm.supportedPct === null && arm.followedPct >= 0,
    ),
  );
});
