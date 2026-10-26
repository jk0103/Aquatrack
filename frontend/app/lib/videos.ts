// Swim videos: the file goes to Firebase Storage at videos/{uid}/{id}.{ext}, and a Firestore
// document at videos/{id} records who uploaded it and what they told us about it.
//
// Fields added after the first uploads (pool length, time, session date, clip length,
// analysis) are optional, so older records still load; `toRecord` fills in the gaps.

import {
  collection,
  doc,
  getDoc,
  getDocs,
  query,
  serverTimestamp,
  setDoc,
  Timestamp,
  where,
  type DocumentData,
} from "firebase/firestore";
import { getDownloadURL, ref, uploadBytesResumable, type UploadTask } from "firebase/storage";

import { parseAnalysis, type AnalysisResult } from "@/app/lib/analysis";
import { db, storage } from "@/app/lib/firebase";

export const MAX_VIDEO_BYTES = 500 * 1024 * 1024; // keep in sync with storage.rules
export const SUGGESTED_MAX_SECONDS = 120;
export const VIDEO_EXTENSIONS = ["mp4", "mov", "m4v", "webm"];

export const STROKES = ["Freestyle", "Backstroke", "Breaststroke", "Butterfly"];
export const CAMERAS = [
  { value: "Underwater", note: "Side view below the surface" },
  { value: "Overhead", note: "From the deck or above the pool" },
  { value: "Side (deck level)", note: "Walking alongside on the pool deck" },
  { value: "Front", note: "Facing the swimmer, head on" },
];
export const DISTANCES = ["25 m", "50 m", "100 m", "200 m", "400 m"];
export const POOL_LENGTHS = ["25 m", "50 m", "25 yd"];

export type VideoStatus = "uploaded" | "analyzing" | "ready" | "failed";

export type VideoDetails = {
  stroke: string;
  camera: string;
  distance: string;
  comments: string;
  wantFeedback: boolean;
  wantPlan: boolean;
  // Optional: missing on records uploaded before these were asked for.
  poolLength?: string;
  timeSeconds?: number;
  sessionDate?: string; // YYYY-MM-DD, the day of the swim
  durationSeconds?: number; // clip length read from the file in the browser
};

export type VideoRecord = VideoDetails & {
  id: string;
  fileName: string;
  sizeBytes: number;
  contentType: string;
  storagePath: string;
  status: VideoStatus;
  createdAt: Date | null;
  // Written by the analysis backend; null until it has run (or if its shape is unknown).
  analysis: AnalysisResult | null;
};

export const statusLabel: Record<VideoStatus, string> = {
  uploaded: "Not analyzed yet",
  analyzing: "Analyzing",
  ready: "Analyzed",
  failed: "Analysis failed",
};

export const statusTone = {
  uploaded: "amber",
  analyzing: "sky",
  ready: "teal",
  failed: "slate",
} as const;

export function fileExtension(name: string): string {
  return name.includes(".") ? name.split(".").pop()!.toLowerCase() : "";
}

// Why this file can't be uploaded, or null if it can.
export function checkVideoFile(file: File): string | null {
  const ext = fileExtension(file.name);
  if (!file.type.startsWith("video/") && !VIDEO_EXTENSIONS.includes(ext)) {
    return "That file isn't a video. Choose an MP4, MOV or WebM file.";
  }
  if (file.size === 0) return "That file is empty.";
  if (file.size > MAX_VIDEO_BYTES) return "Videos must be under 500 MB.";
  return null;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDuration(seconds: number): string {
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function contentTypeFor(file: File): string {
  if (file.type.startsWith("video/")) return file.type;
  const ext = fileExtension(file.name);
  return ext === "mov" ? "video/quicktime" : ext === "webm" ? "video/webm" : "video/mp4";
}

// Uploads the file, then saves its record. `onTask` hands back the upload so it can be
// cancelled; cancelling rejects with a `storage/canceled` error.
export async function uploadVideo(
  uid: string,
  file: File,
  details: VideoDetails,
  onProgress: (fraction: number) => void,
  onTask?: (task: UploadTask) => void,
): Promise<string> {
  const record = doc(collection(db, "videos"));
  const ext = fileExtension(file.name) || "mp4";
  const storagePath = `videos/${uid}/${record.id}.${ext}`;
  const contentType = contentTypeFor(file);

  const task = uploadBytesResumable(ref(storage, storagePath), file, { contentType });
  onTask?.(task);
  await new Promise<void>((resolve, reject) => {
    task.on(
      "state_changed",
      (snap) => onProgress(snap.bytesTransferred / snap.totalBytes),
      reject,
      resolve,
    );
  });

  // Firestore rejects undefined values, so leave out optional fields that weren't given.
  const optional = Object.fromEntries(
    Object.entries(details).filter(([, value]) => value !== undefined),
  );
  await setDoc(record, {
    ...optional,
    uid,
    storagePath,
    fileName: file.name,
    sizeBytes: file.size,
    contentType,
    status: "uploaded",
    createdAt: serverTimestamp(),
  });
  return record.id;
}

const knownStatuses: VideoStatus[] = ["uploaded", "analyzing", "ready", "failed"];

function toRecord(id: string, v: DocumentData): VideoRecord {
  return {
    id,
    stroke: v.stroke ?? "Unknown stroke",
    camera: v.camera ?? "Unknown view",
    distance: v.distance ?? "",
    comments: v.comments ?? "",
    wantFeedback: v.wantFeedback ?? false,
    wantPlan: v.wantPlan ?? false,
    poolLength: typeof v.poolLength === "string" ? v.poolLength : undefined,
    timeSeconds: typeof v.timeSeconds === "number" ? v.timeSeconds : undefined,
    sessionDate: typeof v.sessionDate === "string" ? v.sessionDate : undefined,
    durationSeconds: typeof v.durationSeconds === "number" ? v.durationSeconds : undefined,
    fileName: v.fileName ?? "Video",
    sizeBytes: v.sizeBytes ?? 0,
    contentType: v.contentType ?? "video/mp4",
    storagePath: v.storagePath ?? "",
    status: knownStatuses.includes(v.status) ? v.status : "uploaded",
    createdAt: v.createdAt instanceof Timestamp ? v.createdAt.toDate() : null,
    analysis: parseAnalysis(id, v.analysis),
  };
}

// The user's uploads, newest first.
export async function listVideos(uid: string): Promise<VideoRecord[]> {
  const snap = await getDocs(query(collection(db, "videos"), where("uid", "==", uid)));
  return snap.docs
    .map((d) => toRecord(d.id, d.data()))
    .sort((a, b) => (b.createdAt?.getTime() ?? 0) - (a.createdAt?.getTime() ?? 0));
}

// One upload, or null if it doesn't exist. Someone else's video fails with permission-denied.
export async function getVideo(id: string): Promise<VideoRecord | null> {
  const snap = await getDoc(doc(db, "videos", id));
  return snap.exists() ? toRecord(snap.id, snap.data()) : null;
}

// A short-lived link to play the file; Storage rules only allow the owner.
export function getVideoUrl(record: VideoRecord): Promise<string> {
  return getDownloadURL(ref(storage, record.storagePath));
}

// The day to show for an upload: the swim's date if given, else when it was uploaded.
export function videoDate(v: VideoRecord): Date | null {
  return v.sessionDate ? new Date(`${v.sessionDate}T00:00:00`) : v.createdAt;
}
