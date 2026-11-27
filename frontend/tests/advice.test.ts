// Parser tests for advice documents (src/aquatrack/contracts.py, Advice). Hand-written
// documents in the backend's shape; no model output. Run: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import { categoryLabel, evidenceLabel, parseAdvice, resultHeadline } from "../app/lib/advice.ts";

const suggestion = (n: number, extra: Record<string, unknown> = {}) => ({
  id: `s${n}`,
  title: `Suggestion ${n}`,
  category: "arm_path",
  noticed: "The elbow bend alternates.",
  why_it_may_matter: "It may make the pull harder to repeat.",
  try_this: "Feel the same pressure each pull.",
  drill_id: "tech.catch_up",
  drill_name: "Catch-up freestyle",
  drill_how: "Swim it easily.",
  check_next_time: "Compare successive pulls.",
  confidence: "medium",
  cycles_supporting: 4,
  evidence_refs: ["motion.cycle_to_cycle.elbow_angle_at_mid_pull_deg"],
  times_s: [1.2, 2.4],
  ...extra,
});
const doc = (extra: Record<string, unknown> = {}) => ({
  advice_version: "1.0",
  source: "ai",
  model: "gpt-6.2-astra",
  summary: "A steady rhythm.",
  data_quality: ["One side-on camera."],
  observations: [{ statement: "Cycle time stayed the same.", evidence_refs: ["cycle_duration"], times_s: [] }],
  consistent: [{ statement: "The rhythm repeats.", evidence_refs: [], times_s: [] }],
  suggestions: [suggestion(1)],
  general_practice: [
    { activity_id: "tech.side_kick", name: "Kick on your side", purpose: "Body line.", instructions: ["Kick."], reason: "General." },
  ],
  limitations: ["AI interpretation."],
  created_at: "2026-11-27T10:00:00Z",
  ...extra,
});

test("an AI advice document is read with its three kinds of content kept apart", () => {
  const a = parseAdvice(doc())!;
  assert.equal(a.source, "ai");
  assert.equal(a.suggestions[0].drillName, "Catch-up freestyle");
  assert.equal(a.suggestions[0].cyclesSupporting, 4);
  assert.equal(a.consistent[0].statement, "The rhythm repeats.");
  assert.equal(a.observations.length, 1);
  assert.equal(a.generalPractice[0].activityId, "tech.side_kick");
});

test("a deterministic document never shows suggestions, even if some were stored", () => {
  const a = parseAdvice(doc({ source: "deterministic", fallback_reason: "AI advice is not enabled" }))!;
  assert.equal(a.suggestions.length, 0);
  assert.equal(a.generalPractice.length, 1);
  assert.equal(a.fallbackReason, "AI advice is not enabled");
});

test("at most three suggestions, and incomplete ones are left out", () => {
  const many = [1, 2, 3, 4, 5].map((n) => suggestion(n));
  assert.equal(parseAdvice(doc({ suggestions: many }))!.suggestions.length, 3);
  const broken = [suggestion(1, { noticed: "" }), suggestion(2)];
  assert.deepEqual(parseAdvice(doc({ suggestions: broken }))!.suggestions.map((s) => s.id), ["s2"]);
});

test("unknown versions, unknown sources and non-documents are refused", () => {
  assert.equal(parseAdvice(doc({ advice_version: "2.0" })), null);
  assert.equal(parseAdvice(doc({ source: "something" })), null);
  assert.equal(parseAdvice(null), null);
  assert.equal(parseAdvice("text"), null);
});

test("a minimal document loads with empty lists", () => {
  const a = parseAdvice({ advice_version: "1.0", source: "deterministic" })!;
  assert.deepEqual([a.suggestions, a.observations, a.generalPractice, a.limitations], [[], [], [], []]);
});

test("labels are readable", () => {
  assert.equal(categoryLabel("arm_path"), "Arm pull");
  assert.equal(categoryLabel("unknown"), "Other");
  assert.equal(evidenceLabel("motion.cycle_to_cycle.elbow_angle_at_mid_pull_deg"), "Elbow angle at mid pull");
  assert.equal(evidenceLabel("cycle_duration"), "Cycle duration");
});

test("a tentative suggestion keeps the reasons the backend gave", () => {
  const s = suggestion(1, { tentative: true, tentative_reasons: ["Based on only 3 stroke cycles."] });
  const a = parseAdvice(doc({ suggestions: [s], trusted_cycles: 3 }))!;
  assert.equal(a.suggestions[0].tentative, true);
  assert.deepEqual(a.suggestions[0].tentativeReasons, ["Based on only 3 stroke cycles."]);
  assert.equal(a.trustedCycles, 3);
  assert.equal(parseAdvice(doc())!.suggestions[0].tentative, false); // older documents
});

test("the headline says what kind of evidence there is without overstating it", () => {
  const withAi = parseAdvice(doc({ suggestions: [suggestion(1), suggestion(2)] }));
  const none = parseAdvice(doc({ suggestions: [] }));
  assert.equal(resultHeadline("Uneven stroke rhythm", withAi).title, "Uneven stroke rhythm");
  assert.match(resultHeadline(null, withAi).title, /2 things to try/);
  assert.match(resultHeadline(null, withAi).note, /not a diagnosis/);
  assert.match(resultHeadline(null, parseAdvice(doc())).title, /One thing to try/);
  assert.equal(resultHeadline(null, none).title, "No clear technique issue in this clip");
  assert.equal(resultHeadline(null, null).title, "No clear technique issue in this clip");
  assert.match(resultHeadline(null, none).note, /normal result/);
});
