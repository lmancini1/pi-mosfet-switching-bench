# Raspberry Pi MOSFET switching bench

Tools for running a finite GPIO burst and analyzing oscilloscope captures from
an IRLZ44N switching fixture. The analysis reports VDS transition times,
turn-off voltage peaks, and window energy when a drain-current channel is present.

The included CSV files are **synthetic examples**, not measurements of an IRLZ44N.
No hardware results are included. Use [BENCH_RECORD.md](BENCH_RECORD.md) to record
your fixture and test conditions.

## Try the analysis

Run these commands from the repository directory with Python 3.10 or newer:

```sh
python -m pip install -r requirements-report.txt
python summarize_sweep.py synthetic_sweep.json > sweep.csv
python report_sweep.py synthetic_sweep.json > switching_report.html
```

Open `switching_report.html` in a browser. The report contains individual results,
comparisons by gate resistance and load setting, repeat statistics, and annotated
waveforms. [synthetic_report.html](synthetic_report.html) is a prebuilt example.
For CSV and JSON analysis only, NumPy 2.x is enough:

```sh
python -m pip install 'numpy>=2,<3'
```

## Analyze a scope capture

Export time in seconds and drain-source voltage (VDS) in volts. An optional
drain-current channel must be in amperes, with positive current into the drain.
Calibrate and time-align the voltage and current channels before using energy results.

This example assumes headers named `time_s`, `vds_v`, and `id_a`. Replace the
plateau levels and time windows with values from your capture:

```sh
python analyze_capture.py capture.csv --vds-low 0.1 --vds-high 5 \
  --turn-on 0.000001 0.000002 --turn-off 0.000010 0.000011 \
  --id-column id_a > run.json
```

Omit `--id-column` if you have no current channel. Use `--time-column` and
`--vds-column` for other headers, or `--skip-rows N` for lines before the header.
Samples must be finite, with strictly increasing timestamps.

Choose one clean transition per window. For a low-side MOSFET, VDS falls at
turn-on and rises at turn-off. The script measures 90%–10% fall time and
10%–90% rise time relative to the supplied low and high plateaus. These are VDS
transition times; compare them with datasheet figures only when the signals,
thresholds, and test conditions match.

With a current channel, energy is the signed integral of VDS × ID over the
**entire selected window**, reported in µJ. It depends on the window boundaries,
probe alignment, and calibration; it is not automatically a datasheet switching-loss
measurement. Sample rate and analog bandwidth also limit the transitions you can resolve.

## Compare several captures

Copy [synthetic_sweep.json](synthetic_sweep.json) as a starting point. Keep capture
paths relative to the manifest and set `source` to `measured` for bench data.
Each run needs a unique ID and a separate capture file, plus:

- `gate_resistance_ohm` and `load_current_a`: the test settings.
- `vds_levels_v`: low and high VDS plateaus in volts.
- `turn_on_s` and `turn_off_s`: nonoverlapping analysis windows in seconds.

The manifest's `columns` list gives the time, VDS, and optional current headers,
in that order. The load setting is recorded separately from the instantaneous
current waveform. Keep fixture and acquisition settings consistent across a sweep.

```sh
python summarize_sweep.py my_sweep.json > sweep.csv
python report_sweep.py my_sweep.json > switching_report.html
```

Results are sorted by gate resistance, load setting, and run ID. Energy cells
are blank when there is no current channel. Invalid captures stop processing
before any CSV rows or HTML are written.

The report groups repeats by resistance and load, showing the mean and sample
standard deviation when two or more captures are available. Turn-off peak is the
highest VDS in the selected turn-off window; overshoot is its excess above the
high plateau, floored at zero. Include the transient in that window to compare peaks.

Edges with fewer than five acquired samples between threshold crossings are
marked for review. This is a screening rule, not an accuracy guarantee. Inspect
the traces and sampling intervals before deciding whether to reacquire them.
Save raw captures, the manifest, and the bench record with your results.

## Generate a GPIO burst

Preview the timing without GPIO hardware:

```sh
python run_burst.py --gpio 18 --high-us 10 --low-us 10 --cycles 10000
```

This requests a 50 kHz burst at 50% duty cycle, lasting 0.2 s. `--gpio` uses BCM
numbering; select the channel wired to your fixture.

To emit it, use a Pi supported by your pigpio release, install the `pigpio`
Python module, and start the local `pigpiod` daemon. The script requires exclusive
use of the daemon's waveform transmitter. First disconnect the switching stage
and verify the GPIO waveform on a scope. The active-high GPIO signal is intended
for a separate gate-driver input, with a hardware default-off state for the fixture.

After verifying the setup, add `--emit > burst.json` to the preview command.
The JSON records requested timing, not measured timing. Export the scope capture
separately to measure GPIO timing or device transitions.

## Checks

Run the regression tests with `python -m unittest -v`. GPIO tests use a mock
daemon; they do not verify timing or electrical behavior on a Pi.

## Attribution

The crossing and integration helpers are adapted from chad416's
[sic-double-pulse-test](https://github.com/chad416/sic-double-pulse-test),
`src/dpt/extract.py`. See [LICENSE](LICENSE) for attribution.
