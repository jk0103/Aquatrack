// Still frames from the swimmer's own video that show the feedback's priorities, as the
// backend writes them (src/aquatrack/contracts.py, ProblemFrames). One document at
// videos/{videoId}/frames/{feedbackId}; images are JPEGs in Storage.
//
// Frames only ever illustrate a priority the feedback reported, at the moments its evidence
// names. An empty list is a normal result and carries the reason. Pure parsing: no Firebase.

export type FrameArrow = {
  joint: string; // e.g. "right wrist"
  to: [number, number]; // 0-1 of the image, from that frame's own pose
  labelAt: [number, number];
  label: string;
};

export type ProblemFrame = {
  itemId: string;
  rank: number | null;
  t: number; // seconds into the video
  frameIndex: number;
  cycleIndex: number; // 1-based
  image: string; // Storage path
  width: number;
  height: number;
  arrows: FrameArrow[];
};

export type EmptyReason = "" | "no_issue" | "no_frame_rule" | "no_trusted_frame";

export type ProblemFrames = {
  feedbackId: string;
  frames: ProblemFrame[];
  emptyReason: EmptyReason;
};

export const MAX_FRAMES = 5;
const MAX_LABEL_WORDS = 6;

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj | null => (v && typeof v === "object" ? (v as Obj) : null);
const num = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const reasons: EmptyReason[] = ["", "no_issue", "no_frame_rule", "no_trusted_frame"];

// A point inside the picture, or null. Anything outside 0-1 was not placed by the pose.
function point(v: unknown): [number, number] | null {
  const [x, y] = list(v).map(num);
  return x !== null && y !== null && x >= 0 && x <= 1 && y >= 0 && y <= 1 ? [x, y] : null;
}

function parseArrow(raw: unknown): FrameArrow[] {
  const o = obj(raw);
  const to = point(o?.to);
  const labelAt = point(o?.label_at);
  const label = str(o?.label).trim();
  if (!o || !to || !labelAt || !label) return [];
  return [
    {
      joint: str(o.joint),
      to,
      labelAt,
      label: label.split(/\s+/).slice(0, MAX_LABEL_WORDS).join(" "),
    },
  ];
}

function parseFrame(raw: unknown): ProblemFrame[] {
  const o = obj(raw);
  const t = num(o?.t_s);
  const image = str(o?.image);
  const itemId = str(o?.item_id);
  if (!o || t === null || !image || !itemId) return [];
  // An arrow is the whole point of a problem frame; at most two per frame.
  const arrows = list(o.arrows).flatMap(parseArrow).slice(0, 2);
  if (!arrows.length) return [];
  return [
    {
      itemId,
      rank: num(o.rank),
      t,
      frameIndex: num(o.frame_index) ?? 0,
      cycleIndex: num(o.cycle_index) ?? 0,
      image,
      width: num(o.width) ?? 0,
      height: num(o.height) ?? 0,
      arrows,
    },
  ];
}

export function parseProblemFrames(raw: unknown): ProblemFrames | null {
  const o = obj(raw);
  if (!o || !Array.isArray(o.frames)) return null;
  const frames = o.frames.flatMap(parseFrame).slice(0, MAX_FRAMES);
  const reason = reasons.find((r) => r === o.empty_reason) ?? "";
  return {
    feedbackId: str(o.feedback_id),
    frames,
    emptyReason: frames.length ? "" : reason || "no_trusted_frame",
  };
}

// Only frames for priorities that are in this feedback; never anything else.
export function framesForPriorities(
  frames: ProblemFrames | null,
  priorityIds: string[],
): ProblemFrame[] {
  if (!frames) return [];
  const ids = new Set(priorityIds);
  return frames.frames.filter((f) => ids.has(f.itemId));
}

export function formatClock(t: number): string {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, "0")}`;
}
