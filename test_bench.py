"""Regression checks for analysis boundaries and failed GPIO operations."""

import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from analyze_capture import edge_metrics
from run_burst import Burst, emit
from summarize_sweep import sweep_rows
from waveform_helpers import ExtractionError, crossing_time, integrate


class AnalysisTests(unittest.TestCase):
    def test_crossing_at_first_sample(self):
        for values, direction in (([1., 2.], "rising"), ([1., 0.], "falling")):
            with self.subTest(direction=direction):
                self.assertEqual(crossing_time(np.array([0., 1.]), np.array(values),
                                               1., direction), 0.)

    def test_touching_threshold_without_departing_is_not_a_crossing(self):
        with self.assertRaises(ExtractionError):
            crossing_time(np.array([0., 1.]), np.array([1., 1.]), 1., "rising")

    def test_window_starts_on_first_threshold(self):
        edge = edge_metrics(np.array([0., 1., 2.]), np.array([1., 5., 9.]),
                            None, [0., 2.], 0., 10., "rising")
        self.assertEqual(edge["crossings_s"], [0., 2.])
        self.assertAlmostEqual(edge["duration_ns"], 2e9)

    def test_two_thresholds_in_one_sample_interval(self):
        edge = edge_metrics(np.array([0., 1.]), np.array([10., 0.]),
                            None, [0., 1.], 0., 10., "falling")
        np.testing.assert_allclose(edge["crossings_s"], [.1, .9])
        self.assertEqual(edge["edge_sample_count"], 0)
        self.assertTrue(edge["low_edge_sample_count"])

    def test_integral_interpolates_window_boundaries(self):
        self.assertAlmostEqual(integrate(np.array([0., 1., 2.]),
                                         np.array([0., 2., 4.]), .5, 1.5), 2.)

    def test_synthetic_sweep(self):
        rows = sweep_rows(Path(__file__).parent / "synthetic_sweep.json")
        self.assertEqual(len(rows), 4)
        self.assertEqual([row["gate_resistance_ohm"] for row in rows], [10, 10, 47, 47])
        self.assertTrue(all(row["turn_on_vds_fall_ns"] > 0 for row in rows))


class BurstTests(unittest.TestCase):
    def make_pigpio(self):
        pi = Mock(connected=True)
        pi.wave_tx_busy.return_value = False
        for method in ("write", "wave_add_new", "wave_add_generic", "wave_create",
                       "wave_send_once", "wave_chain"):
            getattr(pi, method).return_value = 0
        return Mock(pi=Mock(return_value=pi)), pi

    def test_negative_wave_creation_is_rejected(self):
        pigpio, pi = self.make_pigpio()
        pi.wave_create.return_value = -67
        with self.assertRaisesRegex(RuntimeError, "-67"):
            emit(Burst(18, 10, 10, 1), pigpio)
        pi.wave_send_once.assert_not_called()
        pi.wave_delete.assert_not_called()
        pi.stop.assert_called_once()

    def test_negative_transmission_status_is_rejected_and_cleaned_up(self):
        for cycles, method in ((1, "wave_send_once"), (2, "wave_chain")):
            with self.subTest(cycles=cycles):
                pigpio, pi = self.make_pigpio()
                getattr(pi, method).return_value = -1
                with self.assertRaisesRegex(RuntimeError, "-1"):
                    emit(Burst(18, 10, 10, cycles), pigpio)
                pi.wave_tx_stop.assert_called_once()
                pi.wave_delete.assert_called_once_with(0)
                pi.write.assert_called_with(18, 0)
                pi.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
