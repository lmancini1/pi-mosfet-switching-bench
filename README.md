# Raspberry Pi IRLZ44N switching bench

## Generate a finite GPIO burst

Preview the requested timing on any computer with Python 3.10+:

```sh
python run_burst.py --gpio 18 --high-us 10 --low-us 10 --cycles 10000
```

This plans a 50 kHz, 50% duty-cycle burst lasting 0.2 s. The GPIO number is
illustrative. Choose the BCM channel wired to your test fixture.

For GPIO output, use a Pi supported by your installed pigpio release, install
its Python module, and start the local pigpiod daemon. Use the daemon
exclusively for the burst. Test with the switching stage disconnected first
and verify the GPIO waveform on the scope. The active-high GPIO output is a
logic signal for a gate-driver input. Use a separate gate driver and a hardware
default-off input for an energized fixture.

To emit the verified burst and record the requested settings, add
`--emit > burst.json`. Export your scope capture separately and run the
analyzer below. The burst JSON records requested GPIO timing. The waveform
CSV is the input for measuring device transition times.

## Analyze the oscilloscope capture

Python post-processing for a Raspberry Pi-controlled switching rig. It takes an
oscilloscope CSV and reports drain-source voltage (VDS) transition times. Your
existing GPIO script can continue to run the test. This program runs after
capture and can run on the Pi or on another computer.

### Run

Install Python 3.10+ and NumPy 2.x. Export time in seconds and VDS in volts. If
available, include a calibrated and time-aligned drain-current channel in amperes,
with positive current into the drain. Use `--time-column`, `--vds-column` and
`--id-column` to select your scope's headers, and `--skip-rows` to skip any
preamble before the header.

Example with illustrative levels and edge windows. Use the levels and windows
from your own capture.

```sh
python -m pip install 'numpy>=2,<3'
python analyze_capture.py capture.csv --vds-low 0.1 --vds-high 5 \
  --turn-on 0.000001 0.000002 --turn-off 0.000010 0.000011 \
  --id-column id_a > run.json
```

Choose one clean transition per window. For a low-side MOSFET, VDS falls at
turn-on and rises at turn-off. The output gives 90%–10% and 10%–90% VDS edge
durations, respectively. These are voltage transition metrics. Compare them with
datasheet values only when the signal, thresholds, and test conditions match.

With a current channel, the script also reports the signed integral of
VDS × ID over each full supplied window. This approximate energy in µJ depends
on window placement, probe alignment, and current calibration. The scope's
sample rate and analog bandwidth determine which transition times it can resolve.

## Compare a gate-resistance and load sweep

```sh
python summarize_sweep.py examples/synthetic_sweep.json > sweep.csv
```

The example uses artificial ramps to exercise the analysis. Copy the manifest to
start a bench sweep. Set `source` to `measured` for your actual scope captures.
Each run records its capture path (relative to the manifest), gate resistance
in ohms, set load current in amperes, VDS plateau levels and two edge windows.
Use a unique run ID for each repeat and record the load setting separately from
the optional instantaneous ID waveform channel.

The summary is sorted by gate resistance and load. Without an ID channel,
energy cells are blank. A failed capture exits with a run number and produces
no comparison rows. Keep the raw captures and manifest beside any published
summary so the results can be reproduced.

## Build the characterization report

Install the report dependency and generate a self-contained HTML file:

```sh
python -m pip install -r requirements-report.txt
python report_sweep.py examples/synthetic_sweep.json > switching_report.html
```

Open the HTML in a browser. It includes the run-by-run results, a comparison
across load settings, and scope traces marked at the exact interpolated
threshold crossings. The run details report sample spacing through each edge
so you can judge how well the scope samples the transition. The synthetic
report is an example of the workflow. Use your scope exports to generate
a report of bench results.

## Run a documented bench campaign

Use [BENCH_RECORD.md](BENCH_RECORD.md) to record the as-built fixture, scope
setup and GPIO verification. The report groups repeat acquisitions by gate
resistance and load setting and shows the sample standard deviation for conditions
with multiple acquisitions. It also reports the highest VDS within each
turn-off window and how far that peak exceeds the supplied high VDS plateau.
The report flags edges with fewer than five acquired samples between the
crossings as a screening heuristic. Flagged runs remain in the summary so
you can inspect their traces and decide whether to reacquire them. Use the same fixture and scope setup across a sweep so the
grouping reflects comparable conditions.

## Source

The crossing and integration helpers are adapted from chad416's
[sic-double-pulse-test](https://github.com/chad416/sic-double-pulse-test),
`src/dpt/extract.py`. See the included MIT license for attribution.
