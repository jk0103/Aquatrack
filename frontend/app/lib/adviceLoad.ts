import { doc, getDoc } from "firebase/firestore";

import { parseAdvice, type Advice } from "@/app/lib/advice";
import { db } from "@/app/lib/firebase";

// The stored advice for one of the swimmer's own videos, or null if it's missing or not
// readable. Reading it never calls a model: the backend made it once, when the video was
// analysed.
export async function loadAdvice(videoId: string, adviceId: string): Promise<Advice | null> {
  const snap = await getDoc(doc(db, "videos", videoId, "advice", adviceId));
  return snap.exists() ? parseAdvice(snap.data()) : null;
}
