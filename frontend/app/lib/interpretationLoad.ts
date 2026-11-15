import { doc, getDoc } from "firebase/firestore";

import { db } from "@/app/lib/firebase";
import { parseInterpretation, type Interpretation } from "@/app/lib/interpretation";

// One interpretation of the swimmer's own video, or null if it's missing or not readable.
export async function loadInterpretation(
  videoId: string,
  interpretationId: string,
): Promise<Interpretation | null> {
  const snap = await getDoc(doc(db, "videos", videoId, "interpretations", interpretationId));
  return snap.exists() ? parseInterpretation(snap.data()) : null;
}
