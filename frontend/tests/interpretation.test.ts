// Parser tests for interpretation documents. Fixtures come from the Python engine run on
// the synthetic swimmer; the "earlier swims" in them are labelled synthetic. Run: npm test
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { parseInterpretation } from "../app/lib/interpretation.ts";

const load = (name: string) =>
  JSON.parse(
    readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8"),
  );

test("a baseline swim has observations and nothing else", () => {
  const i = parseInterpretation(load("interpretation_baseline"));
  assert.ok(i);
  assert.equal(i.baseline, true);
  assert.ok(i.observations.length >= 4);
  assert.ok(
    i.observations.every((f) => f.level === "observation" && !f.actionable),
  );
  assert.deepEqual(i.issueCandidates, []);
  assert.deepEqual(i.priorities, []);
  assert.ok(i.prioritiesNote.length > 0); // the empty section still explains itself
  assert.ok(
    i.undetermined.some(
      (u) => u.key === "no_history" && u.kind === "interpretation",
    ),
  );
  assert.ok(i.rules.some((r) => r.state === "pending_validation"));
});

test("issue candidates, ranked priorities and comparisons keep their evidence", () => {
  const i = parseInterpretation(load("interpretation_with_history"));
  assert.ok(i);
  assert.equal(i.baseline, false);
  assert.ok(i.sessions.every((s) => s.synthetic)); // fixture history is labelled as such
  assert.ok(i.issueCandidates.length >= 1);
  const uneven = i.issueCandidates.find(
    (f) => f.id === "issue.timing.uneven_rhythm",
  );
  assert.ok(uneven && uneven.actionable);
  assert.ok(uneven.evidence.some((e) => e.samples.length === 3));
  assert.ok(i.priorities.length >= 1 && i.priorities.length <= 3);
  assert.deepEqual(
    i.priorities.map((p) => p.rank),
    i.priorities.map((_, k) => k + 1),
  );
  for (const p of i.priorities) {
    assert.ok(i.issueCandidates.some((f) => f.id === p.findingId));
    assert.equal(
      p.score,
      p.factors.reduce((sum, f) => sum + f.points, 0),
    );
  }
  const history = i.observations.filter((f) => f.category === "history");
  assert.ok(history.length > 0 && history.every((f) => f.changes.length > 0));
});

test("a clip nothing could be measured from shows limits, not findings", () => {
  const i = parseInterpretation(load("interpretation_nothing_measured"));
  assert.ok(i);
  assert.deepEqual(
    [i.observations, i.issueCandidates, i.priorities],
    [[], [], []],
  );
  assert.ok(
    i.undetermined.length > 0 &&
      i.undetermined.every((u) => u.title && u.reason),
  );
});

test("a finding can't move up a level, and a priority needs a real issue behind it", () => {
  const doc = load("interpretation_baseline");
  doc.issue_candidates = [{ ...doc.observations[0] }]; // still says level "observation"
  doc.priorities = [
    {
      rank: 1,
      finding_id: "obs.rhythm",
      title: "Made up",
      score: 9,
      factors: [],
    },
  ];
  const i = parseInterpretation(doc);
  assert.ok(i);
  assert.deepEqual(i.issueCandidates, []);
  assert.deepEqual(i.priorities, []);
});

test("never more than three priorities, and unknown documents are rejected", () => {
  const doc = load("interpretation_with_history");
  const one = doc.priorities[0];
  doc.priorities = [1, 2, 3, 4, 5].map((rank) => ({ ...one, rank }));
  assert.equal(parseInterpretation(doc)?.priorities.length, 3);
  assert.equal(parseInterpretation({ interpretation_version: "2.0" }), null);
  assert.equal(parseInterpretation(null), null);
});
