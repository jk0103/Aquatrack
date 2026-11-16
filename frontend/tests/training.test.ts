// Tests for the training and calendar data preparation: reading what the backend sends,
// local dates, the month grid, and editing a session's activity list. All data here is
// SYNTHETIC. Component rendering is not covered by these tests. Run: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  addActivity,
  addCustom,
  addDays,
  basisLabel,
  basisNote,
  byDate,
  checkDraftSession,
  draftMinutes,
  isIsoDate,
  localIso,
  monthGrid,
  parseCalendar,
  parseOverview,
  parsePlan,
  parseSaveResult,
  parseSession,
  removeItem,
  setMinutes,
  sourceLabel,
  statusLabel,
  toDraftItems,
  weekDates,
  weekStart,
  type Activity,
} from "../app/lib/training.ts";

const item = (over = {}) => ({
  activity_id: "warm.easy_swim",
  name: "Easy warm-up swim",
  category: "warm_up",
  minutes: 10,
  distance_m: 250,
  sets: "about 5 x 50 m",
  intensity: "easy",
  instructions: ["Swim easily."],
  source: "recommended",
  recommendation_id: "",
  basis: null,
  evidence_class: "research_supported",
  done: false,
  ...over,
});
const session = (over = {}) => ({
  id: "s1",
  plan_id: "p1",
  plan_version: 1,
  date: "2026-11-16",
  time: "18:00",
  title: "Technique practice",
  minutes: 10,
  basis: "goal_based",
  items: [item()],
  status: "planned",
  origin: "generated",
  ...over,
});
const activity = (over: Partial<Activity> = {}): Activity => ({
  id: "tech.side_kick",
  name: "Kick on your side",
  category: "body_position",
  purpose: "",
  instructions: [],
  min_minutes: 5,
  max_minutes: 10,
  intensity: "easy",
  rest: "",
  equipment: [],
  goals: [],
  watch_for: "",
  video_can_measure: "",
  safety: [],
  evidence_class: "coaching_guidance",
  source_ids: [],
  limitations: [],
  not_offered: null,
  ...over,
});

test("a session is read with safe defaults and unknown values are dropped", () => {
  const s = parseSession(session({ status: "exploded", basis: "ai_optimized", completion: null }));
  assert.equal(s.status, "planned");
  assert.equal(s.basis, null);
  assert.equal(s.items[0].source, "recommended");
  assert.equal(s.checkpoint, null);
  assert.equal(s.linked_video_id, "");
  assert.equal(parseSession({ date: "16/11/2026" }).date, "");
  assert.equal(parseSession(null).items.length, 0);
});

test("a plan without a real start date is not shown at all", () => {
  assert.equal(parsePlan({ title: "x", start_date: "soon" }), null);
  const plan = parsePlan({
    title: "Week from 2026-11-16",
    start_date: "2026-11-16",
    end_date: "2026-11-22",
    kind: "week",
    basis: "goal_based",
    sessions: [session(), session({ date: "nope" })],
    rest_days: [{ date: "2026-11-17", guidance: "Rest." }, { date: "x" }],
    inputs: { analysis_removed: true },
  });
  assert.ok(plan);
  assert.equal(plan.sessions.length, 1);
  assert.equal(plan.rest_days.length, 1);
  assert.equal(plan.inputs.analysis_removed, true);
  assert.equal(plan.explanation.source, "template");
});

test("the overview, calendar and save answers are read, and junk is refused", () => {
  assert.equal(parseOverview({}), null);
  const view = parseOverview({
    swimmer: { level: "hobby", goals: ["speed"], missing: ["available days"] },
    week: { start: "2026-11-16", end: "2026-11-22", planned: 2, completed: 1 },
    analysis: { state: "made_up" },
    sources: [{ id: "x", url: "javascript:alert(1)" }],
    library: [activity(), { name: "no id" }],
  });
  assert.ok(view);
  assert.equal(view.analysis.state, "none");
  assert.equal(view.sources[0].url, ""); // only https links are ever rendered
  assert.equal(view.library.length, 1);
  assert.deepEqual(view.week, { start: "2026-11-16", end: "2026-11-22", planned: 2, completed: 1, skipped: 0, canceled: 0 });
  assert.equal(view.llm_enabled, false);
  assert.equal(parseCalendar({ sessions: [session()], rest_days: [{ date: "bad" }] }).rest_days.length, 0);
  assert.equal(parseSaveResult({ saved: true }), null);
  const conflict = parseSaveResult({ saved: false, conflict: { kind: "week_overlap", plans: [{ id: "p", edited: 1 }] } });
  assert.ok(conflict && !conflict.saved && conflict.conflict.plans[0].edited === 1);
});

test("labels never call a swimmer's own activity a recommendation or a goal plan a diagnosis", () => {
  assert.equal(sourceLabel("manual"), "Added by you");
  assert.equal(sourceLabel("modified"), "Changed by you");
  assert.equal(basisLabel(null), "Created by you");
  assert.match(basisNote("goal_based"), /does not mean a problem was found/);
  assert.match(basisNote("analysis_based"), /not a confirmed fault/);
  assert.equal(statusLabel("canceled"), "Cancelled");
  for (const b of ["analysis_based", "goal_based", "general", null] as const)
    assert.doesNotMatch(basisLabel(b) + basisNote(b), /optimi[sz]ed|AI|guarantee/i);
});

test("dates stay on the swimmer's own calendar day", () => {
  assert.equal(localIso(new Date(2026, 10, 16, 23, 59)), "2026-11-16"); // late evening stays today
  assert.equal(localIso(new Date(2026, 0, 1, 0, 0)), "2026-01-01");
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
  assert.equal(addDays("2028-02-28", 1), "2028-02-29"); // leap year
  assert.equal(addDays("2026-03-01", -1), "2026-02-28");
  assert.equal(addDays("2026-03-29", 1), "2026-03-30"); // across a clock change
  assert.equal(addDays("2026-10-25", 1), "2026-10-26");
  assert.ok(isIsoDate("2028-02-29"));
  assert.ok(!isIsoDate("2026-02-29") && !isIsoDate("2026-13-01") && !isIsoDate("2026-1-1"));
});

test("weeks start on Monday and the month grid covers whole weeks", () => {
  assert.equal(weekStart("2026-11-16"), "2026-11-16"); // a Monday
  assert.equal(weekStart("2026-11-22"), "2026-11-16"); // the Sunday of that week
  assert.deepEqual(weekDates("2026-11-19"), ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-21", "2026-11-22"]);
  const nov = monthGrid(2026, 10);
  assert.equal(nov[0][0], "2026-10-26");
  assert.equal(nov.at(-1)![6], "2026-12-06");
  assert.ok(nov.every((row) => row.length === 7));
  assert.ok(nov.flat().includes("2026-11-01") && nov.flat().includes("2026-11-30"));
  assert.equal(new Set(nov.flat()).size, nov.flat().length); // no day twice
  const feb = monthGrid(2027, 1); // 1 Feb 2027 is a Monday: exactly four rows
  assert.equal(feb.length, 4);
  assert.equal(feb[0][0], "2027-02-01");
});

test("sessions are grouped by their own date", () => {
  const map = byDate([parseSession(session()), parseSession(session({ id: "s2" })), parseSession(session({ id: "s3", date: "2026-11-18" }))]);
  assert.equal(map.get("2026-11-16")!.length, 2);
  assert.equal(map.get("2026-11-18")!.length, 1);
  assert.equal(map.get("2026-11-17"), undefined);
});

test("editing a draft: change minutes, remove, add from the library, add your own", () => {
  let items = toDraftItems([parseSession(session()).items[0]]);
  items = setMinutes(items, 0, 15);
  assert.equal(items[0].minutes, 15);
  items = addActivity(items, activity());
  assert.deepEqual(items[1], { activity_id: "tech.side_kick", name: "Kick on your side", minutes: 5 });
  assert.equal(addActivity(items, activity()).length, 2); // never listed twice
  items = addCustom(items, "  Backstroke for fun ");
  assert.deepEqual(items[2], { activity_id: "", name: "Backstroke for fun", minutes: 10 });
  assert.equal(addCustom(items, "   ").length, 3);
  assert.equal(draftMinutes(items), 30);
  assert.deepEqual(removeItem(items, 1).map((i) => i.name), ["Easy warm-up swim", "Backstroke for fun"]);
});

test("an impossible draft gets one clear message before anything is sent", () => {
  const library = [activity({ id: "warm.easy_swim", name: "Easy warm-up swim", min_minutes: 5, max_minutes: 15 }), activity()];
  const ok = { date: "2026-11-16", time: "", title: "Swim", items: [{ activity_id: "warm.easy_swim", name: "Easy warm-up swim", minutes: 10 }] };
  assert.equal(checkDraftSession(ok, library), null);
  const bad = (change: object) => checkDraftSession({ ...ok, ...change }, library) ?? "";
  assert.match(bad({ date: "2026-02-30" }), /Choose a date/);
  assert.match(bad({ time: "7pm" }), /HH:MM/);
  assert.match(bad({ title: "  " }), /title/);
  assert.match(bad({ items: [] }), /at least one activity/);
  assert.match(bad({ items: [{ ...ok.items[0], minutes: 40 }] }), /between 5 and 15/);
  assert.match(bad({ items: [{ ...ok.items[0], minutes: NaN }] }), /whole number/);
  assert.match(bad({ items: [{ activity_id: "made.up", name: "Mystery", minutes: 5 }] }), /not in the activity library/);
  assert.match(bad({ items: [{ activity_id: "", name: "Mine", minutes: 500 }] }), /between 1 and 120/);
  assert.match(bad({ items: [{ activity_id: "", name: "A", minutes: 120 }, { activity_id: "", name: "B", minutes: 100 }] }), /under 180/);
});
