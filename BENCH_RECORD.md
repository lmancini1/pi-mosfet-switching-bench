# IRLZ44N bench record

## Question

At a fixed load and unchanged fixture, how does gate resistance affect VDS
transition time and peak turn-off VDS? Include window energy if calibrated,
time-aligned drain current is available.

## Fixture and instrument record

| Item | Record for this campaign |
| --- | --- |
| Campaign ID, date, operator | |
| DUT marking and fixture revision | |
| Schematic and as-built fixture photo filenames | |
| Raspberry Pi model, BCM pin and burst JSON filename | |
| Gate driver part and supply setting | |
| Supply setting, load setting and load type | |
| Scope model, sample rate, bandwidth setting | |
| VDS probe model, attenuation and reference point | |
| Current probe or shunt, scale, sign and deskew method | |
| Trigger channel and acquisition mode | |
| Temperature or warm-up notes | |

## Acquisition sequence

1. Capture the GPIO burst with the switching stage disconnected. Record measured
   frequency, duty cycle and any mismatch with the requested burst settings.
2. Define three gate-resistance settings feasible for the existing fixture. Keep
   the load, driver settings, probes and scope settings fixed across those conditions.
3. Record at least three independent scope acquisitions per setting, with a unique
   capture and manifest ID for each acquisition. Cycle through the settings or
   revisit the baseline at the end to check for drift. Log any rejected trace
   and the reason in the bench notes.
4. Use consistent threshold and window-selection rules. Include the turn-off
   transient in the turn-off window if you plan to compare peaks. Capture the
   same portion of the burst for each run.
5. Generate the CSV and HTML report. Save the scope exports, manifest, GPIO
   check, fixture details and report together.

## Results to fill in after testing

- Measured GPIO frequency and duty cycle
- Conditions compared and capture count per condition
- Change in turn-on and turn-off transition times
- Change in turn-off peak VDS and, where available, window energy
- Whether the change was large relative to the between-capture spread
- How sample spacing, probe bandwidth and deskew affected interpretation
- One design decision supported by the measurements
