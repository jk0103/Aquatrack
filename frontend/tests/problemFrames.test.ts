// Parser tests for problem-frame documents (src/aquatrack/contracts.py, ProblemFrames).
// Hand-written documents in the backend's shape; no real video. Run: npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  formatClock,
  framesForPriorities,
  parseProblemFrames,
} from "../app/lib/problemFrames.ts";

const arrow = (label = "Longer cycle: 1.44 s (usual 1.20)") => ({
  joint: "right wrist",
  to: [0.45, 0.7],
  label_at: [0.37, 0.5],
  label,
});
const frame = (n: number, extra: Record<string, unknown> = {}) => ({
  item_id: "fb.priority.issue.timing.uneven_rhythm",
  rank: 1,
  t_s: n,
  frame_index: n * 25,
  cycle_index: n,
  image: `analysis/u/v/a/frames/f/${n}.jpg`,
  width: 1280,
  height: 720,
  arrows: [arrow()],
  ...extra,
});

test("frames are read with their arrows, at most five", () => {
  const doc = { feedback_id: "f", frames: [1, 2, 3, 4, 5, 6, 7].map((n) => frame(n)) };
  const parsed = parseProblemFrames(doc);
  assert.ok(parsed);
  assert.equal(parsed.frames.length, 5);
  assert.deepEqual(parsed.frames[0].arrows[0].to, [0.45, 0.7]);
  assert.equal(parsed.emptyReason, "");
});

test("a frame without a usable arrow or image is dropped, and labels are cut to six words", () => {
  const parsed = parseProblemFrames({
    frames: [
      frame(1, { arrows: [] }),
      frame(2, { image: "" }),
      frame(3, { arrows: [{ ...arrow(), to: [1.4, 0.2] }] }), // outside the picture
      frame(4, { arrows: [arrow("one two three four five six seven eight")] }),
    ],
  });
  assert.ok(parsed);
  assert.equal(parsed.frames.length, 1);
  assert.equal(parsed.frames[0].arrows[0].label, "one two three four five six");
});

test("an empty document keeps its reason; an unknown or missing reason reads as no trusted frame", () => {
  assert.equal(parseProblemFrames({ frames: [], empty_reason: "no_issue" })?.emptyReason, "no_issue");
  assert.equal(parseProblemFrames({ frames: [], empty_reason: "nope" })?.emptyReason, "no_trusted_frame");
  assert.equal(parseProblemFrames({ frames: [frame(1, { arrows: [] })] })?.emptyReason, "no_trusted_frame");
  assert.equal(parseProblemFrames(null), null);
  assert.equal(parseProblemFrames({}), null);
});

test("only frames for priorities in this feedback are shown", () => {
  const parsed = parseProblemFrames({
    frames: [frame(1), frame(2, { item_id: "fb.issue.something_else" })],
  });
  assert.deepEqual(
    framesForPriorities(parsed, ["fb.priority.issue.timing.uneven_rhythm"]).map((f) => f.t),
    [1],
  );
  assert.deepEqual(framesForPriorities(parsed, []), []);
  assert.deepEqual(framesForPriorities(null, ["x"]), []);
});

test("timestamps read as minutes and seconds", () => {
  assert.equal(formatClock(3.24), "0:03.24");
  assert.equal(formatClock(65.5), "1:05.50");
});
