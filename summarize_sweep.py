"""Analyze a manifest of MOSFET scope captures and write a comparison CSV."""

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from itertools import groupby
from statistics import mean, stdev

from analyze_capture import analyze_waveforms, read_capture
from waveform_helpers import ExtractionError


def number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return value


def pair(value, label):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} must be a pair")
    low, high = [number(item, label) for item in value]
    if low >= high:
        raise ValueError(f"{label} must be strictly increasing")
    return low, high


def analyze_sweep(manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    source = manifest.get("source")
    if source not in ("measured", "synthetic"):
        raise ValueError("source must be measured or synthetic")
    columns = manifest.get("columns", ["time_s", "vds_v"])
    if (
        not isinstance(columns, list) or len(columns) not in (2, 3)
        or any(not isinstance(column, str) or not column.strip() for column in columns)
        or len(set(columns)) != len(columns)
    ):
        raise ValueError("columns must list distinct time, VDS and optionally ID headers in order")
    skip_rows = manifest.get("skip_rows", 0)
    if type(skip_rows) is not int or skip_rows < 0:
        raise ValueError("skip_rows must be a nonnegative integer")
    runs = manifest.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("runs must be a nonempty list")

    run_ids = set()
    capture_paths = set()
    for index, run in enumerate(runs, start=1):
        try:
            run_id = run["id"]
            if not isinstance(run_id, str) or not run_id.strip() or run_id in run_ids:
                raise ValueError("id must be a unique nonempty string")
            capture = run["capture"]
            if not isinstance(capture, str) or not capture.strip():
                raise ValueError("capture must be a path to a CSV file")
            capture_path = (manifest_path.parent / capture).resolve()
            if capture_path in capture_paths:
                raise ValueError("capture is already assigned to another run")
            resistance = number(run["gate_resistance_ohm"], "gate_resistance_ohm")
            load = number(run["load_current_a"], "load_current_a")
            if resistance < 0 or load < 0:
                raise ValueError("gate resistance and load current must be nonnegative")
            low, high = pair(run["vds_levels_v"], "vds_levels_v")
            turn_on = pair(run["turn_on_s"], "turn_on_s")
            turn_off = pair(run["turn_off_s"], "turn_off_s")
            if max(turn_on[0], turn_off[0]) < min(turn_on[1], turn_off[1]):
                raise ValueError("turn-on and turn-off windows overlap")
            samples = read_capture(capture_path, columns, skip_rows)
            metrics = analyze_waveforms(capture_path, samples, low, high, turn_on, turn_off)
        except (ValueError, TypeError, KeyError, OSError, ExtractionError) as exc:
            raise ValueError(f"run {index}: {exc}") from exc

        run_ids.add(run_id)
        capture_paths.add(capture_path)
        on = metrics["turn_on_vds_fall"]
        off = metrics["turn_off_vds_rise"]
        row = {
            "source": source,
            "run_id": run_id,
            "capture": capture,
            "gate_resistance_ohm": resistance,
            "load_current_a": load,
            "turn_on_vds_fall_ns": on["duration_ns"],
            "turn_off_vds_rise_ns": off["duration_ns"],
            "turn_off_window_peak_vds_v": off["window_peak_vds_v"],
            "turn_off_window_overshoot_v": off["window_peak_above_high_v"],
            "turn_on_edge_samples": on["edge_sample_count"],
            "turn_off_edge_samples": off["edge_sample_count"],
            "low_edge_sample_count": on["low_edge_sample_count"] or off["low_edge_sample_count"],
            "turn_on_window_energy_uj": on.get("vds_id_window_energy_uj"),
            "turn_off_window_energy_uj": off.get("vds_id_window_energy_uj"),
        }
        yield row, metrics, samples


def sweep_key(row):
    return row["gate_resistance_ohm"], row["load_current_a"], row["run_id"]


def sweep_rows(manifest_path):
    return sorted((row for row, _, _ in analyze_sweep(manifest_path)), key=sweep_key)


def repeatability(rows):
    """Group separate acquisitions made at the same resistance and load setting."""
    fields = (
        "turn_on_vds_fall_ns",
        "turn_off_vds_rise_ns",
        "turn_off_window_peak_vds_v",
        "turn_off_window_overshoot_v",
        "turn_on_window_energy_uj",
        "turn_off_window_energy_uj",
    )
    for settings, group in groupby(sorted(rows, key=sweep_key), key=lambda row: sweep_key(row)[:2]):
        runs = list(group)
        metrics = {}
        for field in fields:
            values = [row[field] for row in runs if row[field] is not None]
            metrics[field] = {
                "n": len(values),
                "mean": mean(values) if values else None,
                "sd": stdev(values) if len(values) >= 2 else None,
            }
        yield {
            "gate_resistance_ohm": settings[0],
            "load_current_a": settings[1],
            "runs": len(runs),
            "metrics": metrics,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        rows = sweep_rows(args.manifest)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


if __name__ == "__main__":
    main()
