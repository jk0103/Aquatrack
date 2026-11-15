import { doc, getDoc } from "firebase/firestore";

import { parseFeedback, type Feedback } from "@/app/lib/feedback";
import { db } from "@/app/lib/firebase";

// The feedback for one of the swimmer's own videos, or null if it's missing or not readable.
export async function loadFeedback(videoId: string, feedbackId: string): Promise<Feedback | null> {
  const snap = await getDoc(doc(db, "videos", videoId, "feedback", feedbackId));
  return snap.exists() ? parseFeedback(snap.data()) : null;
}
