"""Analyze one IRLZ44N oscilloscope capture from a CSV file."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from waveform_helpers import ExtractionError, crossing_time, integrate


MIN_EDGE_SAMPLES = 5


def read_capture(path, columns, skip_rows):
    with path.open(newline="", encoding="utf-8-sig") as source:
        for _ in range(skip_rows):
            next(source, None)
        reader = csv.DictReader(source)
        if reader.fieldnames is None or any(
            reader.fieldnames.count(column) != 1 for column in columns
        ):
            raise ValueError(f"expected unique CSV columns {columns}; found {reader.fieldnames}")
        try:
            rows = [
                [float(row[column]) for column in columns]
                for row in reader
            ]
        except (ValueError, TypeError) as exc:
            raise ValueError(f"non-numeric sample on CSV row {reader.line_num + skip_rows}") from exc
    samples = np.asarray(rows, dtype=float)
    if len(samples) < 2 or not np.isfinite(samples).all():
        raise ValueError("capture must contain at least two rows with finite samples")
    if np.any(np.diff(samples[:, 0]) <= 0):
        raise ValueError("timestamps must be strictly increasing")
    return samples.T


def edge_metrics(time, voltage, current, window, low, high, direction):
    start, stop = window
    if not time[0] <= start < stop <= time[-1]:
        raise ValueError(f"{direction} window must lie within the capture and have positive duration")
    inside = (time > start) & (time < stop)
    edge_time = np.concatenate(([start], time[inside], [stop]))
    edge_voltage = np.interp(edge_time, time, voltage)
    lower = low + 0.1 * (high - low)
    upper = low + 0.9 * (high - low)
    first, second = (lower, upper) if direction == "rising" else (upper, lower)
    begin = crossing_time(edge_time, edge_voltage, first, direction)
    # Search from the interpolated first crossing so a single sample interval can
    # legitimately bracket both thresholds.
    later = edge_time > begin
    end = crossing_time(
        np.concatenate(([begin], edge_time[later])),
        np.concatenate(([first], edge_voltage[later])),
        second,
        direction,
    )
    intervals = (time[:-1] < end) & (time[1:] > begin)
    peak_index = int(np.argmax(edge_voltage))
    edge_sample_count = int(np.count_nonzero((time >= begin) & (time <= end)))
    result = {
        "duration_ns": (end - begin) * 1e9,
        "window_s": [start, stop],
        "crossings_s": [begin, end],
        "window_peak_vds_v": float(edge_voltage[peak_index]),
        "window_peak_time_s": float(edge_time[peak_index]),
        "window_peak_above_high_v": float(max(0, edge_voltage[peak_index] - high)),
        "edge_sample_count": edge_sample_count,
        "low_edge_sample_count": edge_sample_count < MIN_EDGE_SAMPLES,
        "thresholds_v": [first, second],
        "max_sample_interval_ns": float(np.max(np.diff(time)[intervals]) * 1e9),
    }
    if current is not None:
        result["vds_id_window_energy_uj"] = (
            integrate(time, voltage * current, start, stop) * 1e6
        )
    return result


def analyze_capture(path, columns, skip_rows, low, high, turn_on, turn_off):
    samples = read_capture(path, columns, skip_rows)
    return analyze_waveforms(path, samples, low, high, turn_on, turn_off)


def analyze_waveforms(path, samples, low, high, turn_on, turn_off):
    time, voltage, *extra = samples
    current = extra[0] if extra else None
    return {
        "capture": str(path),
        "vds_levels_v": [low, high],
        "turn_on_vds_fall": edge_metrics(time, voltage, current, turn_on, low, high, "falling"),
        "turn_off_vds_rise": edge_metrics(time, voltage, current, turn_off, low, high, "rising"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--time-column", default="time_s")
    parser.add_argument("--vds-column", default="vds_v")
    parser.add_argument("--id-column", help="Calibrated drain current column in amperes")
    parser.add_argument("--skip-rows", type=int, default=0, help="Lines before CSV header")
    parser.add_argument("--vds-low", type=float, required=True)
    parser.add_argument("--vds-high", type=float, required=True)
    parser.add_argument("--turn-on", type=float, nargs=2, metavar=("START_S", "STOP_S"), required=True)
    parser.add_argument("--turn-off", type=float, nargs=2, metavar=("START_S", "STOP_S"), required=True)
    args = parser.parse_args()
    if args.skip_rows < 0:
        parser.error("--skip-rows must be nonnegative")
    if not np.isfinite([args.vds_low, args.vds_high]).all() or args.vds_low >= args.vds_high:
        parser.error("VDS levels must be finite and low must be strictly below high")

    columns = [args.time_column, args.vds_column]
    if args.id_column:
        columns.append(args.id_column)
    if len(set(columns)) != len(columns):
        parser.error("time, voltage and current must use distinct columns")
    try:
        result = analyze_capture(
            args.capture, columns, args.skip_rows, args.vds_low, args.vds_high,
            args.turn_on, args.turn_off,
        )
    except (OSError, ValueError, ExtractionError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
