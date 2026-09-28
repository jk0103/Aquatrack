import numpy as np

from aquatrack.analysis.pose import Joint
from aquatrack.analysis.pose.yolo_backend import select_swimmer


def test_select_swimmer_picks_largest_person():
    xyn = np.zeros((2, 17, 2))
    xyn[0, :, 0] = 0.1  # small person far away
    xyn[1, :, 0] = 0.7  # large person being filmed
    xyn[1, 10] = (0.8, 0.3)  # their right wrist in COCO order
    conf = np.full((2, 17), 0.9)
    boxes = np.array([[0.1, 0.5, 0.05, 0.1], [0.6, 0.5, 0.5, 0.3]])

    points = select_swimmer(xyn, conf, boxes)

    assert points.shape == (len(Joint), 3)
    assert tuple(points[Joint.RIGHT_WRIST]) == (0.8, 0.3, 0.9)
    assert np.all(points[:, 0] >= 0.7)


def test_select_swimmer_no_detection():
    points = select_swimmer(np.empty((0, 17, 2)), None, np.empty((0, 4)))
    assert np.isnan(points).all()
