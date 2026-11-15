// Parser tests for feedback documents. Fixtures come from the Python builder run on the
// synthetic swimmer with labelled synthetic history and a mocked model. Run: npm test
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { parseFeedback } from "../app/lib/feedback.ts";

const load = (name: string) =>
  JSON.parse(
    readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8"),
  );
const of = (f: NonNullable<ReturnType<typeof parseFeedback>>, c: string) =>
  f.items.filter((i) => i.category === c);

test("goals add general information, kept apart from what was measured", () => {
  const f = parseFeedback(load("feedback_goals_no_issues"));
  assert.ok(f);
  assert.deepEqual([of(f, "priority"), of(f, "focus")], [[], []]);
  assert.ok(of(f, "observation").length >= 4);
  const education = of(f, "education");
  assert.equal(education.length, 2);
  for (const item of education) {
    assert.equal(item.personal, false);
    assert.equal(item.confidence, "general");
    assert.deepEqual(item.evidence, []); // general information carries no measurements
    assert.equal(item.rank, null);
    assert.ok(
      item.text.startsWith(
        "General information, not a finding about your swimming.",
      ),
    );
  }
  assert.ok(
    f.references.length >= 2 &&
      f.references.every((r) => r.url.startsWith("https://doi.org/")),
  );
  assert.ok(f.checkpoints.some((c) => c.id === "cp.repeat_same_conditions"));
  assert.equal(f.explanationSource, "template");
});

test("priorities come first, ranked, with their reasons and reworded text", () => {
  const f = parseFeedback(load("feedback_priorities_reworded"));
  assert.ok(f);
  const priorities = of(f, "priority");
  assert.ok(priorities.length >= 1 && priorities.length <= 3);
  assert.deepEqual(
    priorities.map((p) => p.rank),
    priorities.map((_, k) => k + 1),
  );
  assert.equal(f.items[0].category, "priority");
  assert.ok(
    priorities.every(
      (p) => p.whyItMayMatter && p.factors.length > 0 && p.monitor,
    ),
  );
  assert.equal(f.explanationSource, "llm");
  assert.ok(f.items.some((i) => i.reworded));
  assert.ok(f.checkpoints.some((c) => c.id.startsWith("cp.recurs.")));
});

test("a video nothing could be measured from still gives limits, tips and a checkpoint", () => {
  const f = parseFeedback(load("feedback_nothing_measured"));
  assert.ok(f);
  assert.deepEqual(
    [of(f, "observation"), of(f, "focus"), of(f, "priority")],
    [[], [], []],
  );
  assert.ok(of(f, "insufficient").length > 0);
  assert.ok(f.recordingTips.length >= 4);
  assert.deepEqual(
    f.checkpoints.map((c) => c.id),
    ["cp.side_view"],
  );
});

test("a document can't dress general information up as a personal finding", () => {
  const doc = load("feedback_goals_no_issues");
  const education = doc.items.find(
    (i: { category: string }) => i.category === "education",
  );
  education.personal = true;
  education.rank = 1;
  education.evidence = [
    { metric_key: "stroke_rate", label: "x", value: 50, samples: [] },
  ];
  education.why_it_may_matter = "Because your stroke is uneven.";
  const f = parseFeedback(doc);
  assert.ok(f);
  const parsed = of(f, "education")[0];
  assert.equal(parsed.personal, false);
  assert.equal(parsed.rank, null);
  assert.deepEqual(parsed.evidence, []);
  assert.equal(parsed.whyItMayMatter, "");
});

test("only doi.org links are shown, at most three priorities, unknown versions rejected", () => {
  const doc = load("feedback_priorities_reworded");
  doc.references[0].url = "https://example.com/paper";
  const one = doc.items.find(
    (i: { category: string }) => i.category === "priority",
  );
  doc.items = [1, 2, 3, 4, 5]
    .map((rank) => ({ ...one, id: `${one.id}.${rank}`, rank }))
    .concat(doc.items);
  const f = parseFeedback(doc);
  assert.ok(f);
  assert.equal(f.references[0].url, "");
  assert.equal(of(f, "priority").length, 3);
  assert.equal(parseFeedback({ feedback_version: "2.0" }), null);
  assert.equal(parseFeedback(null), null);
});
