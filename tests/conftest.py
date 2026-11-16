from pathlib import Path

import cv2
import numpy as np
import pytest


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    """A 1-second 64x48 synthetic video at 10 fps."""
    path = tmp_path / "sample.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
    for i in range(10):
        frame = np.full((48, 64, 3), i * 20, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return path


# ---------- shared fixtures for the analysis pipeline, sources and jobs ----------

import synthetic  # noqa: E402

from aquatrack.analysis.video import video_identity  # noqa: E402
from aquatrack.contracts import (  # noqa: E402
    BoxSource,
    ModelConfig,
    ModelInfo,
    Provenance,
    RawPose,
    RawPoseMeta,
    Selection,
)

SWIM_FRAMES = 250


@pytest.fixture(scope="session")
def swim_video(tmp_path_factory) -> Path:
    """A blank video with the synthetic swimmer's frame count, rate and aspect ratio.
    The pictures don't matter: pose data for it comes from `make_raw_pose`."""
    path = tmp_path_factory.mktemp("swim") / "swim.mp4"
    size = (synthetic.W // 4, synthetic.H // 4)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), synthetic.FPS, size)
    for i in range(SWIM_FRAMES):
        writer.write(np.full((size[1], size[0], 3), i % 255, dtype=np.uint8))
    writer.release()
    return path


def make_raw_pose(video_path: Path | None = None, xy: np.ndarray | None = None, **meta) -> RawPose:
    """A schema-v1 RawPose of the synthetic swimmer, with a box around the body each frame."""
    if xy is None:
        xy = synthetic.swimmer_xy(synthetic.times(SWIM_FRAMES))
    n = len(xy)
    if video_path is not None:
        identity = video_identity(video_path)
        width, height = identity.width, identity.height
    else:
        identity, width, height = None, synthetic.W, synthetic.H
    keypoints = np.concatenate([xy / (synthetic.W, synthetic.H), np.full((n, 133, 1), 6.0)], -1)
    body = keypoints[:, :17, :2] * (width, height)
    boxes = np.concatenate([body.min(axis=1) - 5, body.max(axis=1) + 5], axis=1)
    fields = {
        "video": identity,
        "fps": float(synthetic.FPS),
        "width": width,
        "height": height,
        "config": ModelConfig(),
        "detector": ModelInfo(name="yolo11m.pt"),
        "pose": ModelInfo(name="rtmw_x_stock.onnx"),
        "provenance": Provenance(source="precomputed", produced_by="test"),
    } | meta
    return RawPose(
        meta=RawPoseMeta(**fields),
        frame_indices=np.arange(n),
        timestamps_s=np.arange(n) / synthetic.FPS,
        keypoints=keypoints,
        boxes=boxes,
        box_confidence=np.full(n, 0.9),
        box_source=np.full(n, int(BoxSource.DETECTED), np.uint8),
        selection=np.full(n, int(Selection.OVERLAP), np.uint8),
        candidates=np.ones(n, np.int16),
    )


@pytest.fixture(autouse=True)
def fresh_request_limits():
    """Request limits are counted per process; each test starts from zero."""
    from aquatrack.api.limits import limiter

    limiter.reset()
    yield
