"""Small signal helpers for keypoint time series."""

import numpy as np


def fill_gaps(values: np.ndarray) -> np.ndarray:
    """Linearly interpolate NaNs (frames where the joint was not detected)."""
    values = np.asarray(values, dtype=float)
    mask = np.isnan(values)
    if mask.all():
        return values
    idx = np.arange(len(values))
    filled = values.copy()
    filled[mask] = np.interp(idx[mask], idx[~mask], values[~mask])
    return filled


def smooth(values: np.ndarray, window: int) -> np.ndarray:
    """Centered moving average."""
    if window <= 1:
        return values
    kernel = np.ones(window) / window
    return np.convolve(values, kernel, mode="same")


def find_peaks(values: np.ndarray, min_distance: int) -> np.ndarray:
    """Indices of local maxima at least `min_distance` samples apart."""
    candidates = np.where((values[1:-1] > values[:-2]) & (values[1:-1] >= values[2:]))[0] + 1
    peaks: list[int] = []
    for i in candidates[np.argsort(values[candidates])[::-1]]:
        if all(abs(i - p) >= min_distance for p in peaks):
            peaks.append(int(i))
    return np.array(sorted(peaks), dtype=int)
