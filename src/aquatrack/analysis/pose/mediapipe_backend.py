"""MediaPipe Pose backend. Needs the optional extra: `uv sync --extra pose`.

Good enough to prototype on deck/overhead video. Expect dropped frames underwater
(bubbles, refraction, body cut by the surface line) until a swim-specific model is trained.
"""

import numpy as np

from aquatrack.analysis.pose.base import Joint, PoseSequence
from aquatrack.analysis.video import iter_frames, read_video_info

# MediaPipe Pose landmark index for each Joint
_MP_INDEX = {
    Joint.NOSE: 0,
    Joint.LEFT_SHOULDER: 11,
    Joint.RIGHT_SHOULDER: 12,
    Joint.LEFT_ELBOW: 13,
    Joint.RIGHT_ELBOW: 14,
    Joint.LEFT_WRIST: 15,
    Joint.RIGHT_WRIST: 16,
    Joint.LEFT_HIP: 23,
    Joint.RIGHT_HIP: 24,
    Joint.LEFT_KNEE: 25,
    Joint.RIGHT_KNEE: 26,
    Joint.LEFT_ANKLE: 27,
    Joint.RIGHT_ANKLE: 28,
}


class MediaPipePoseEstimator:
    def __init__(self, min_detection_confidence: float = 0.5):
        try:
            import mediapipe as mp
        except ImportError as e:
            raise ImportError("Install the pose extra: uv sync --extra pose") from e
        self._pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            min_detection_confidence=min_detection_confidence,
        )

    def estimate(self, video_path: str, step: int = 1) -> PoseSequence:
        import cv2

        info = read_video_info(video_path)
        frames = []
        for _, frame in iter_frames(video_path, step=step):
            result = self._pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            points = np.full((len(Joint), 3), np.nan)
            if result.pose_landmarks:
                landmarks = result.pose_landmarks.landmark
                for joint, mp_index in _MP_INDEX.items():
                    lm = landmarks[mp_index]
                    points[joint] = (lm.x, lm.y, lm.visibility)
            frames.append(points)
        keypoints = np.stack(frames) if frames else np.empty((0, len(Joint), 3))
        return PoseSequence(keypoints=keypoints, fps=info.fps / step)
