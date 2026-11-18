import { doc, getDoc } from "firebase/firestore";
import { getDownloadURL, ref } from "firebase/storage";

import { db, storage } from "@/app/lib/firebase";
import { parseProblemFrames, type ProblemFrames } from "@/app/lib/problemFrames";

export type LoadedFrames = ProblemFrames & { urls: Record<string, string> };

// The frames chosen for one feedback document, with a link for each image. null when the
// worker has not stored any for this feedback (an older analysis, or a re-run without video).
export async function loadProblemFrames(
  videoId: string,
  feedbackId: string,
): Promise<LoadedFrames | null> {
  const snap = await getDoc(doc(db, "videos", videoId, "frames", feedbackId));
  const parsed = snap.exists() ? parseProblemFrames(snap.data()) : null;
  if (!parsed) return null;
  const urls: Record<string, string> = {};
  const kept = [];
  for (const f of parsed.frames) {
    try {
      urls[f.image] = await getDownloadURL(ref(storage, f.image));
      kept.push(f);
    } catch {
      // A missing image is left out rather than shown broken.
    }
  }
  return {
    ...parsed,
    frames: kept,
    emptyReason: kept.length ? "" : parsed.emptyReason || "no_trusted_frame",
    urls,
  };
}
