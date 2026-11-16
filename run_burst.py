"""Preview or emit a finite, active-high GPIO pulse train with pigpio."""

import argparse
import json
import signal
import time
from contextlib import ExitStack
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Burst:
    gpio: int
    high_us: int
    low_us: int
    cycles: int

    @property
    def period_us(self):
        return self.high_us + self.low_us


def emit(burst, pigpio):
    pi = pigpio.pi("localhost")
    with ExitStack() as cleanup:
        cleanup.callback(pi.stop)
        if not pi.connected:
            raise RuntimeError("could not connect to local pigpiod")
        if pi.wave_tx_busy():
            raise RuntimeError("pigpiod is already transmitting a wave")

        pi.write(burst.gpio, 0)
        pi.wave_add_new()
        mask = 1 << burst.gpio
        pi.wave_add_generic([
            pigpio.pulse(mask, 0, burst.high_us),
            pigpio.pulse(0, mask, burst.low_us),
        ])
        wave_id = pi.wave_create()
        cleanup.callback(pi.wave_delete, wave_id)
        # On abort, stop DMA and drive low before trying to delete its wave.
        cleanup.callback(pi.write, burst.gpio, 0)
        cleanup.callback(pi.wave_tx_stop)
        if burst.cycles == 1:
            pi.wave_send_once(wave_id)
        else:
            pi.wave_chain([255, 0, wave_id, 255, 1, burst.cycles & 255, burst.cycles >> 8])

        deadline = time.monotonic() + burst.period_us * burst.cycles / 1e6 + 2
        while pi.wave_tx_busy():
            if time.monotonic() >= deadline:
                raise RuntimeError("timed out waiting for the GPIO burst")
            time.sleep(0.005)


def interrupt(_signum, _frame):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpio", type=int, required=True, help="BCM GPIO number")
    parser.add_argument("--high-us", type=int, required=True)
    parser.add_argument("--low-us", type=int, required=True)
    parser.add_argument("--cycles", type=int, required=True)
    parser.add_argument("--emit", action="store_true", help="enable actual GPIO output")
    args = parser.parse_args()
    if not 2 <= args.gpio <= 27:
        parser.error("--gpio must be a BCM header GPIO from 2 through 27")
    if min(args.high_us, args.low_us) < 1 or args.high_us + args.low_us > 1_000_000:
        parser.error("high and low must each be positive and total at most 1,000,000 µs")
    if not 1 <= args.cycles <= 65535:
        parser.error("--cycles must be between 1 and 65535")

    burst = Burst(args.gpio, args.high_us, args.low_us, args.cycles)
    if args.emit:
        signal.signal(signal.SIGTERM, interrupt)
        try:
            import pigpio
        except ImportError:
            parser.exit(1, "GPIO output requires the pigpio Python module and local pigpiod\n")
        try:
            emit(burst, pigpio)
        except KeyboardInterrupt:
            parser.exit(130, "GPIO burst interrupted\n")
        except (OSError, RuntimeError, pigpio.error) as exc:
            parser.exit(1, f"GPIO error: {exc}\n")

    print(json.dumps({
        "status": "emitted" if args.emit else "preview",
        **asdict(burst),
        "requested_frequency_hz": 1e6 / burst.period_us,
        "requested_duty_cycle": burst.high_us / burst.period_us,
        "planned_duration_s": burst.period_us * burst.cycles / 1e6,
    }, indent=2))


if __name__ == "__main__":
    main()
