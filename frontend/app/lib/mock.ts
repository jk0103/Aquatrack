// Placeholder data for the UI layout. Replace with API calls once the endpoints exist.

// Fixed "today" so the mock calendar and week view line up.
export const TODAY = "2026-10-15";

export type Stroke = "Freestyle" | "Backstroke" | "Breaststroke" | "Butterfly";

export type Analysis = {
  id: string;
  date: string;
  stroke: Stroke;
  camera: "Underwater" | "Overhead";
  distance: string;
  score: number;
  headline: string;
  comment: string;
  status: "Ready" | "Processing";
};

export const analyses: Analysis[] = [
  {
    id: "a-1042",
    date: "2026-10-10",
    stroke: "Freestyle",
    camera: "Underwater",
    distance: "50 m",
    score: 78,
    headline: "Crossover on the left hand entry",
    comment: "Felt like I was pulling harder on my right side.",
    status: "Ready",
  },
  {
    id: "a-1041",
    date: "2026-10-14",
    stroke: "Butterfly",
    camera: "Overhead",
    distance: "25 m",
    score: 0,
    headline: "Analyzing your video",
    comment: "Second kick feels weak near the end.",
    status: "Processing",
  },
  {
    id: "a-1038",
    date: "2026-10-03",
    stroke: "Freestyle",
    camera: "Overhead",
    distance: "100 m",
    score: 74,
    headline: "Head lifts during breathing",
    comment: "Race pace 100, tired on the last length.",
    status: "Ready",
  },
  {
    id: "a-1031",
    date: "2026-09-26",
    stroke: "Butterfly",
    camera: "Underwater",
    distance: "25 m",
    score: 69,
    headline: "Hips sink after the first kick",
    comment: "",
    status: "Ready",
  },
  {
    id: "a-1027",
    date: "2026-09-19",
    stroke: "Freestyle",
    camera: "Underwater",
    distance: "50 m",
    score: 71,
    headline: "Early catch drops the elbow",
    comment: "Working on high elbow drills this week.",
    status: "Ready",
  },
];

export type FeedbackPoint = {
  title: string;
  severity: "Focus" | "Watch" | "Good";
  detail: string;
  drill: string;
};

export const feedback: FeedbackPoint[] = [
  {
    title: "Left hand crosses the centre line",
    severity: "Focus",
    detail:
      "Your left hand enters about 10 cm past your head's centre line, which pushes your hips to the right and costs you a straight path.",
    drill: "Catch-up freestyle with a pull buoy, 4 × 50 m, enter at shoulder width.",
  },
  {
    title: "Breathing timing is late",
    severity: "Watch",
    detail:
      "You turn to breathe after your hand has already started the pull, so the head lifts slightly to find air.",
    drill: "Side-kick 6-3-6 drill, 4 × 25 m, rotate with the body not the neck.",
  },
  {
    title: "Strong, steady flutter kick",
    severity: "Good",
    detail: "Kick amplitude stays compact and consistent through the whole length.",
    drill: "Keep it up. No change needed.",
  },
];

export type TrainingPlan = {
  id: string;
  name: string;
  focus: string;
  week: number;
  weeks: number;
  done: number;
  total: number;
  next: string;
};

export const trainingPlans: TrainingPlan[] = [
  {
    id: "t-1",
    name: "Straight-line freestyle",
    focus: "Hand entry and body alignment",
    week: 2,
    weeks: 4,
    done: 5,
    total: 12,
    next: "Catch-up drill set, 1,800 m",
  },
  {
    id: "t-2",
    name: "Butterfly rhythm",
    focus: "Two-kick timing and hip drive",
    week: 1,
    weeks: 3,
    done: 1,
    total: 9,
    next: "Single-arm fly, 1,200 m",
  },
  {
    id: "t-3",
    name: "Race pace 100 free",
    focus: "Holding pace on the last 25",
    week: 3,
    weeks: 6,
    done: 8,
    total: 18,
    next: "Broken 100s at goal pace, 2,400 m",
  },
];

export type CalendarEvent = {
  date: string;
  title: string;
  kind: "Training" | "Meet";
  time?: string;
  place?: string;
};

export const events: CalendarEvent[] = [
  { date: "2026-10-05", title: "Aerobic base", kind: "Training", time: "6:00 AM" },
  { date: "2026-10-07", title: "Catch-up drills", kind: "Training", time: "6:00 AM" },
  { date: "2026-10-09", title: "Race pace 100s", kind: "Training", time: "6:00 PM" },
  { date: "2026-10-12", title: "Single-arm fly", kind: "Training", time: "6:00 AM" },
  { date: "2026-10-14", title: "Catch-up drills", kind: "Training", time: "6:00 AM" },
  { date: "2026-10-15", title: "Aerobic base", kind: "Training", time: "6:00 AM" },
  { date: "2026-10-16", title: "Broken 100s", kind: "Training", time: "6:00 PM" },
  {
    date: "2026-10-18",
    title: "Fall Invitational",
    kind: "Meet",
    time: "8:00 AM",
    place: "City Aquatic Center",
  },
  { date: "2026-10-21", title: "Recovery swim", kind: "Training", time: "6:00 AM" },
  { date: "2026-10-23", title: "Butterfly rhythm", kind: "Training", time: "6:00 PM" },
  { date: "2026-10-26", title: "Aerobic base", kind: "Training", time: "6:00 AM" },
  {
    date: "2026-10-31",
    title: "Club Time Trials",
    kind: "Meet",
    time: "9:00 AM",
    place: "Riverside Pool",
  },
];

export type TimeEntry = { date: string; seconds: number; meet?: boolean };

// Personal times by event, oldest first.
export const progression: Record<string, TimeEntry[]> = {
  "100 m Freestyle": [
    { date: "2026-05-02", seconds: 64.8, meet: true },
    { date: "2026-06-06", seconds: 64.1 },
    { date: "2026-06-27", seconds: 63.5 },
    { date: "2026-07-18", seconds: 63.7, meet: true },
    { date: "2026-08-15", seconds: 62.6 },
    { date: "2026-09-05", seconds: 62.2, meet: true },
    { date: "2026-09-26", seconds: 61.7 },
    { date: "2026-10-09", seconds: 61.3 },
  ],
  "50 m Freestyle": [
    { date: "2026-05-02", seconds: 29.4, meet: true },
    { date: "2026-06-13", seconds: 29.1 },
    { date: "2026-07-18", seconds: 28.8, meet: true },
    { date: "2026-08-22", seconds: 28.9 },
    { date: "2026-09-05", seconds: 28.4, meet: true },
    { date: "2026-10-03", seconds: 28.1 },
  ],
  "50 m Butterfly": [
    { date: "2026-05-02", seconds: 33.2, meet: true },
    { date: "2026-06-20", seconds: 32.9 },
    { date: "2026-07-18", seconds: 32.4, meet: true },
    { date: "2026-08-29", seconds: 32.5 },
    { date: "2026-09-26", seconds: 31.8 },
  ],
};

export function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(2).padStart(5, "0");
  return m > 0 ? `${m}:${s}` : (seconds % 60).toFixed(2);
}

export function formatDate(iso: string, opts: Intl.DateTimeFormatOptions = {}): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    ...opts,
  });
}

// Measurements shown on the feedback page for the example freestyle 50 m.
export const swimMetrics = {
  lapMeters: 50,
  atMeters: 32,
  clock: "0:20.4",
  lapTime: "31.80",
  split25: "15.40",
  strokeRate: 46, // strokes per minute
  strokeRateTarget: [40, 50] as [number, number],
  distancePerStroke: 1.85,
  breaths: 6,
  kick: "6-beat",
  rotationDeg: 38,
};
