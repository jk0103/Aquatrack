import { doc, getDoc } from "firebase/firestore";

import { parseAnalysisV1, type AnalysisV1 } from "@/app/lib/analysisV1";
import { db } from "@/app/lib/firebase";

// One analysis run of the swimmer's own video, or null if it's missing or not readable.
export async function loadAnalysis(videoId: string, analysisId: string): Promise<AnalysisV1 | null> {
  const snap = await getDoc(doc(db, "videos", videoId, "analyses", analysisId));
  return snap.exists() ? parseAnalysisV1(snap.data()) : null;
}
