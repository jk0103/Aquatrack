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
