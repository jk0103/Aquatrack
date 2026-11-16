import type { ReactNode } from "react";

function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-xl bg-sky-50 px-3.5 py-2.5 text-sm text-sky-950">
      <span className="mt-0.5 shrink-0 rounded-full bg-sky-100 px-2 text-xs font-semibold">
        Demo
      </span>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

// Shown where a video is uploaded in the demonstration environment.
export function DemoUploadNotice() {
  return (
    <Notice>
      <p>
        This is a demonstration environment. It analyses one approved test
        video: &ldquo;Front Crawl Underwater&rdquo; (Wikimedia Commons, by
        &ldquo;It is a wonderful world&rdquo;, CC BY-SA 4.0).
      </p>
      <p>
        The swimmer&apos;s body positions in that video were extracted in
        advance by pretrained AI pose-estimation models (YOLO11m and RTMW-x).
        Those models were not trained by AquaTrack and do not run on this
        site. When you analyze the video, AquaTrack matches the uploaded file
        to that saved pose data and calculates the measurements,
        interpretation and feedback from it.
      </p>
      <p>Any other video can&apos;t be analysed here and will say so.</p>
    </Notice>
  );
}

// Shown on a result whose pose data was not produced by a model run on this upload.
export function SavedPoseNotice() {
  return (
    <Notice>
      <p>
        The pose data behind this result was extracted earlier from this
        exact video by pretrained AI pose-estimation models. It was not
        produced by a live model run. The measurements and feedback were
        calculated from that pose data by AquaTrack.
      </p>
    </Notice>
  );
}
