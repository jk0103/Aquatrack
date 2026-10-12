// Swim videos: the file goes to Firebase Storage at videos/{uid}/{id}.{ext}, and a Firestore
// document at videos/{id} records who uploaded it and what they told us about it.

import {
  collection,
  doc,
  getDocs,
  query,
  serverTimestamp,
  setDoc,
  Timestamp,
  where,
} from "firebase/firestore";
import { ref, uploadBytesResumable } from "firebase/storage";

import { db, storage } from "@/app/lib/firebase";

export const MAX_VIDEO_BYTES = 500 * 1024 * 1024; // keep in sync with storage.rules

export type VideoDetails = {
  stroke: string;
  camera: string;
  distance: string;
  comments: string;
  wantFeedback: boolean;
  wantPlan: boolean;
};

export type VideoRecord = VideoDetails & {
  id: string;
  fileName: string;
  sizeBytes: number;
  status: "uploaded" | "analyzing" | "ready";
  createdAt: Date | null;
};

export async function uploadVideo(
  uid: string,
  file: File,
  details: VideoDetails,
  onProgress: (fraction: number) => void,
): Promise<string> {
  const record = doc(collection(db, "videos"));
  const ext = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "mp4";
  const storagePath = `videos/${uid}/${record.id}.${ext}`;

  const task = uploadBytesResumable(ref(storage, storagePath), file, {
    contentType: file.type || "video/mp4",
  });
  await new Promise<void>((resolve, reject) => {
    task.on(
      "state_changed",
      (snap) => onProgress(snap.bytesTransferred / snap.totalBytes),
      reject,
      resolve,
    );
  });

  await setDoc(record, {
    ...details,
    uid,
    storagePath,
    fileName: file.name,
    sizeBytes: file.size,
    contentType: file.type || "video/mp4",
    status: "uploaded",
    createdAt: serverTimestamp(),
  });
  return record.id;
}

// The user's uploads, newest first.
export async function listVideos(uid: string): Promise<VideoRecord[]> {
  const snap = await getDocs(query(collection(db, "videos"), where("uid", "==", uid)));
  return snap.docs
    .map((d) => {
      const v = d.data();
      return {
        id: d.id,
        stroke: v.stroke,
        camera: v.camera,
        distance: v.distance,
        comments: v.comments,
        wantFeedback: v.wantFeedback,
        wantPlan: v.wantPlan,
        fileName: v.fileName,
        sizeBytes: v.sizeBytes,
        status: v.status,
        createdAt: v.createdAt instanceof Timestamp ? v.createdAt.toDate() : null,
      };
    })
    .sort((a, b) => (b.createdAt?.getTime() ?? 0) - (a.createdAt?.getTime() ?? 0));
}
