"""Numerical helpers adapted from src/dpt/extract.py in chad416/sic-double-pulse-test."""

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]


class ExtractionError(RuntimeError):
    """Raised when a crossing cannot be located."""


def crossing_time(
    t: FloatArray,
    y: FloatArray,
    level: float,
    direction: str,
    t_start: float | None = None,
    t_stop: float | None = None,
) -> float:
    """First time in ``[t_start, t_stop]`` where ``y`` crosses ``level``.

    ``direction`` is ``"rising"`` or ``"falling"``. The crossing instant is
    linearly interpolated between the two bracketing samples.
    """
    if direction not in ("rising", "falling"):
        raise ValueError("direction must be 'rising' or 'falling'")
    lo = 0 if t_start is None else int(np.searchsorted(t, t_start, side="left"))
    hi = len(t) if t_stop is None else int(np.searchsorted(t, t_stop, side="right"))
    ys = y[lo:hi] - level
    # Include a window that starts exactly on the threshold and departs in
    # the requested direction, without counting a flat threshold plateau.
    if direction == "rising":
        crosses = ((ys[:-1] < 0) & (ys[1:] >= 0)) | ((ys[:-1] == 0) & (ys[1:] > 0))
    else:
        crosses = ((ys[:-1] > 0) & (ys[1:] <= 0)) | ((ys[:-1] == 0) & (ys[1:] < 0))
    idx = np.nonzero(crosses)[0]
    if idx.size == 0:
        raise ExtractionError(f"no {direction} crossing of {level:.4g} in [{t_start}, {t_stop}]")
    k = lo + int(idx[0])
    y0, y1 = y[k] - level, y[k + 1] - level
    frac = 0.0 if y1 == y0 else -y0 / (y1 - y0)
    return float(t[k] + frac * (t[k + 1] - t[k]))


def integrate(t: FloatArray, y: FloatArray, t0: float, t1: float) -> float:
    """Trapezoidal integral of ``y`` over ``[t0, t1]`` with interpolated end points."""
    if not t[0] <= t0 < t1 <= t[-1]:
        raise ValueError("integration window must lie within the capture and have positive duration")
    inner = (t > t0) & (t < t1)
    ts = np.concatenate(([t0], t[inner], [t1]))
    ys = np.concatenate(([np.interp(t0, t, y)], y[inner], [np.interp(t1, t, y)]))
    return float(np.trapezoid(ys, ts))
