"""Render an offline HTML report with sweep comparisons and annotated scope captures."""

import argparse
from base64 import b64encode
from html import escape
from io import BytesIO
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np

from analyze_capture import MIN_EDGE_SAMPLES
from summarize_sweep import analyze_sweep, repeatability, sweep_key


EDGES = (
    ("turn_on_vds_fall", "Turn-on · VDS fall"),
    ("turn_off_vds_rise", "Turn-off · VDS rise"),
)


def inline_figure(fig, alt):
    buffer = BytesIO()
    FigureCanvasAgg(fig).print_png(buffer)
    pixels = b64encode(buffer.getvalue()).decode("ascii")
    return f'<img alt="{escape(alt)}" src="data:image/png;base64,{pixels}">'


def plot_run(metrics, samples):
    time, voltage, *extra = samples
    fig = Figure(figsize=(9.5, 3.25), layout="constrained", dpi=120)
    for ax, (key, label) in zip(fig.subplots(1, 2), EDGES):
        edge = metrics[key]
        start, stop = edge["window_s"]
        begin, end = edge["crossings_s"]
        lo = max(0, np.searchsorted(time, start, side="right") - 1)
        hi = min(len(time), np.searchsorted(time, stop, side="left") + 1)
        x = (time[lo:hi] - start) * 1e9
        ax.plot(x, voltage[lo:hi], ".-", color="#117a84", label="VDS samples")
        ax.axvspan((begin - start) * 1e9, (end - start) * 1e9, color="#e1a030", alpha=0.25)
        ax.scatter((np.asarray([begin, end]) - start) * 1e9, edge["thresholds_v"],
                   color="#a45d00", zorder=3, label="Interpolated crossings")
        if key == "turn_off_vds_rise":
            ax.axhline(metrics["vds_levels_v"][1], color="#667780", linestyle=":",
                       label="High plateau reference")
            ax.scatter((edge["window_peak_time_s"] - start) * 1e9, edge["window_peak_vds_v"],
                       marker="^", color="#b33955", zorder=4, label="Window peak")
        ax.set(xlim=(0, (stop - start) * 1e9), xlabel="Time from window start (ns)",
               ylabel="VDS (V)", title=label)
        ax.grid(alpha=0.2)
        ax.legend(loc="best", fontsize=7)
        if extra:
            current_axis = ax.twinx()
            current_axis.plot(x, extra[0][lo:hi], "--", color="#6f55a2", alpha=0.75)
            current_axis.set_ylabel("Drain current (A)", color="#6f55a2")
    return inline_figure(fig, "Turn-on and turn-off waveforms with highlighted threshold crossings")


def plot_comparison(rows):
    fig = Figure(figsize=(9.5, 3.25), layout="constrained", dpi=120)
    loads = sorted({row["load_current_a"] for row in rows})
    panels = [(f"{key}_ns", label, "Transition time (ns)") for key, label in EDGES]
    panels.append(("turn_off_window_overshoot_v", "Turn-off overshoot", "Above high plateau (V)"))
    for ax, (field, label, units) in zip(fig.subplots(1, 3), panels):
        for load in loads:
            points = [row for row in rows if row["load_current_a"] == load]
            ax.scatter([row["gate_resistance_ohm"] for row in points],
                       [row[field] for row in points], label=f"{load:g} A")
        ax.set(xlabel="Gate resistance (Ω)", ylabel=units, title=label)
        ax.grid(alpha=0.2)
        ax.legend(title="Set load current", fontsize=8)
    return inline_figure(fig, "Switching times and turn-off overshoot versus gate resistance")



def metric_note(metrics):
    details = []
    for key, label in EDGES:
        edge = metrics[key]
        duration = edge["duration_ns"]
        interval = edge["max_sample_interval_ns"]
        details.append(
            f"{label}: {duration:.4g} ns. Largest sample interval intersecting the "
            f"threshold-to-threshold span: {interval:.4g} ns. "
            f"Acquired samples across the edge: {edge['edge_sample_count']}."
            + (" Review sampling resolution." if edge["low_edge_sample_count"] else "")
        )
    return " ".join(details)


def format_cell(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.5g}"
    return escape(str(value))


def repeatability_table(rows, fields):
    headers = ("Gate resistance (Ω)", "Load setting (A)", "Runs", *fields.values())
    headings = "".join(f'<th scope="col">{label}</th>' for label in headers)
    body = []
    for group in repeatability(rows):
        cells = [format_cell(group[key]) for key in ("gate_resistance_ohm", "load_current_a", "runs")]
        for field in fields:
            stat = group["metrics"][field]
            value = format_cell(stat["mean"])
            if stat["sd"] is not None:
                value += f" ± {format_cell(stat['sd'])}"
            cells.append(value)
        body.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    return (
        f'<div class="table-wrap"><table><thead><tr>{headings}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


def render_report(manifest):
    runs = []
    for row, metrics, samples in analyze_sweep(manifest):
        runs.append((row, metric_note(metrics), plot_run(metrics, samples)))
    runs.sort(key=lambda run: sweep_key(run[0]))
    rows = [row for row, _, _ in runs]
    synthetic = rows[0]["source"] == "synthetic"
    provenance = (
        "Synthetic example · not bench measurements"
        if synthetic else "Measured sweep · supplied scope captures"
    )
    fields = {
        "run_id": "Run",
        "gate_resistance_ohm": "Gate resistance (Ω)",
        "load_current_a": "Load setting (A)",
        "turn_on_vds_fall_ns": "Turn-on fall (ns)",
        "turn_off_vds_rise_ns": "Turn-off rise (ns)",
        "turn_off_window_peak_vds_v": "Turn-off peak (V)",
        "turn_off_window_overshoot_v": "Overshoot (V)",
        "turn_on_window_energy_uj": "Turn-on window (µJ)",
        "turn_off_window_energy_uj": "Turn-off window (µJ)",
    }
    review_count = sum(row["low_edge_sample_count"] for row in rows)
    headings = "".join(f'<th scope="col">{label}</th>' for label in fields.values())
    body = "\n".join(
        "<tr>" + "".join(f"<td>{format_cell(row[key])}</td>" for key in fields)
        + ("<td>Review</td>" if row["low_edge_sample_count"] else "<td>—</td>") + "</tr>"
        for row in rows
    )
    sections = "\n".join(
        f"<section><h3>{escape(row['run_id'])}</h3>"
        f"<p>Capture <code>{escape(row['capture'])}</code></p>{figure}<p>{note}</p></section>"
        for row, note, figure in runs
    )
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IRLZ44N switching results</title>
<style>
body {{ max-width: 68rem; padding: 1.5rem; margin: auto; color: #172833;
       font: 1rem/1.5 system-ui, sans-serif; background: #f8fafb; }}
h1, h2, h3 {{ line-height: 1.2; }}
.provenance {{ border-left: 4px solid #117a84; padding-left: .75rem; font-weight: 600; }}
section {{ margin: 1rem 0; background: white; border: 1px solid #d8e1e5; padding: 1rem; }}
img {{ width: 100%; height: auto; }}
.table-wrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }}
th, td {{ padding: .5rem; border-bottom: 1px solid #d8e1e5; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
</style>
<main>
<h1>IRLZ44N switching results</h1>
<p class="provenance">{provenance}</p>
<h2>Sweep results</h2>
<div class="table-wrap"><table><thead><tr>{headings}<th scope="col">Sampling</th></tr></thead><tbody>{body}</tbody></table></div>
<p>Each point represents one capture. Energy integrates signed VDS × ID over the full
operator-selected window. A dash in the energy columns indicates a missing current channel.</p>
<p>{review_count} of {len(rows)} runs contain an edge with fewer than {MIN_EDGE_SAMPLES}
acquired samples between its threshold crossings. The Review flag is a sampling check, not an accuracy estimate.
Flagged runs remain visible in the tables and plots.</p>
{plot_comparison(rows)}
<h2>Repeatability by test condition</h2>
<p>Values are mean ± sample standard deviation when at least two captures are
available. A single capture has no spread estimate. This spread describes repeatability.
Turn-off peak is the highest VDS in the selected window and depends on capture bandwidth
and sampling. Overshoot is the peak above the user-supplied high plateau, floored at zero.</p>
{repeatability_table(rows, {key: label for key, label in fields.items() if key.endswith(("_ns", "_v", "_uj"))})}
<h2>Scope traces</h2>
<p>Markers show linearly interpolated 10% and 90% VDS crossings. Sample spacing
describes capture resolution through the edge. Probe bandwidth and channel alignment
also affect measurement accuracy.</p>
{sections}
</main>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        report = render_report(args.manifest)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(report)


if __name__ == "__main__":
    main()
