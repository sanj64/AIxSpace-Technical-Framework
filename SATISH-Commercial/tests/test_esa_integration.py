"""Tests for ESA-ADB ingestion, the D1 degenerate-window guard, and the replay source."""

from __future__ import annotations

import numpy as np
import pandas as pd

from satish_commercial.detectors import CausalZScoreDetector
from satish_commercial.ingest.esa_adb import (
    _anomaly_label,
    _causal_align,
    build_dataset,
    derive_physical_bounds,
)
from satish_commercial.live import REPLAY_SOURCE, ReplayTelemetrySource

# --- ETL: causal alignment ------------------------------------------------------------


def test_causal_align_uses_last_prior_value_never_future() -> None:
    times = pd.to_datetime(
        ["2004-01-01T00:00:00Z", "2004-01-01T00:10:00Z"], utc=True
    )
    series = pd.Series([10.0, 20.0], index=times)
    grid = pd.date_range("2004-01-01T00:00:00Z", "2004-01-01T00:15:00Z", freq="5min", tz="UTC")
    aligned = _causal_align(series, grid, max_gap_seconds=600.0)
    # 00:00 -> 10 (own obs); 00:05 -> 10 (carried, not the future 20); 00:10 -> 20; 00:15 -> 20.
    assert list(aligned.to_numpy()) == [10.0, 10.0, 20.0, 20.0]


def test_causal_align_leaves_stale_gap_as_nan() -> None:
    times = pd.to_datetime(["2004-01-01T00:00:00Z"], utc=True)
    series = pd.Series([10.0], index=times)
    grid = pd.date_range("2004-01-01T00:00:00Z", "2004-01-01T01:00:00Z", freq="5min", tz="UTC")
    aligned = _causal_align(series, grid, max_gap_seconds=600.0)
    assert aligned.iloc[0] == 10.0
    # Beyond the 600s tolerance the carried value expires -> NaN (row will DEGRADE downstream).
    assert bool(np.isnan(aligned.iloc[-1]))


# --- ETL: interval -> binary label ----------------------------------------------------


def test_anomaly_label_marks_only_covered_grid_points() -> None:
    grid = pd.date_range("2004-01-01T00:00:00Z", "2004-01-01T01:00:00Z", freq="15min", tz="UTC")
    labels = pd.DataFrame(
        {
            "Channel": ["channel_1"],
            "StartTime": pd.to_datetime(["2004-01-01T00:20:00Z"], utc=True),
            "EndTime": pd.to_datetime(["2004-01-01T00:40:00Z"], utc=True),
        }
    )
    flags = _anomaly_label(
        labels,
        grid,
        channels=("channel_1",),
        window_start=grid[0],
        window_end=grid[-1],
    )
    # grid: 00:00, 00:15, 00:30, 00:45, 01:00 -> only 00:30 is inside [00:20, 00:40].
    assert list(flags) == [0, 0, 1, 0, 0]


def test_anomaly_label_is_global_or_across_channels() -> None:
    grid = pd.date_range("2004-01-01T00:00:00Z", "2004-01-01T00:30:00Z", freq="15min", tz="UTC")
    labels = pd.DataFrame(
        {
            "Channel": ["channel_1", "channel_2"],
            "StartTime": pd.to_datetime(
                ["2004-01-01T00:00:00Z", "2004-01-01T00:30:00Z"], utc=True
            ),
            "EndTime": pd.to_datetime(
                ["2004-01-01T00:00:00Z", "2004-01-01T00:30:00Z"], utc=True
            ),
        }
    )
    flags = _anomaly_label(
        labels, grid, channels=("channel_1", "channel_2"), window_start=grid[0], window_end=grid[-1]
    )
    # grid: 00:00, 00:15, 00:30 -> channel_1 covers 00:00, channel_2 covers 00:30 (global OR).
    assert list(flags) == [1, 0, 1]


def test_derive_physical_bounds_envelops_observed_range() -> None:
    frame = pd.DataFrame({"channel_1": [1.0, 2.0, 3.0]})
    bounds = derive_physical_bounds(frame, ("channel_1",), margin=0.1)
    assert bounds["channel_1"]["min"] < 1.0
    assert bounds["channel_1"]["max"] > 3.0


# --- D1: degenerate-window guard ------------------------------------------------------


def _degenerate_detector() -> CausalZScoreDetector:
    detector = CausalZScoreDetector(("a",), window=5, minimum_threshold=3.0)
    # A perfectly constant training/calibration window: std == 0 (the stuck-sensor case).
    detector.fit(np.full((5, 1), 4.2))
    detector.calibrate(np.full((5, 1), 4.2))
    return detector


def test_degenerate_window_step_is_flagged_anomalous_not_missed() -> None:
    detector = _degenerate_detector()
    result = detector.score_one(np.array([9.9]), update_reference=False)
    assert result.anomaly is True
    assert result.detector_evidence["degenerate_reference_window"] is True


def test_degenerate_window_no_deviation_stays_nominal() -> None:
    detector = _degenerate_detector()
    result = detector.score_one(np.array([4.2]), update_reference=False)
    assert result.anomaly is False
    assert result.detector_evidence["degenerate_reference_window"] is False


# --- Live: recorded replay source -----------------------------------------------------


def _replay_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [
                "2004-10-15T00:00:00.000Z",
                "2004-10-15T00:05:00.000Z",
            ],
            "a": [1.0, float("nan")],
            "b": [2.0, 3.0],
            "mission_phase": ["OPERATIONS", "OPERATIONS"],
        }
    )


def test_replay_source_streams_real_values_with_provenance() -> None:
    source = ReplayTelemetrySource(("a", "b"), _replay_frame())
    first = source.next_sample(1)
    assert first.source == REPLAY_SOURCE
    assert first.channel_values == {"a": 1.0, "b": 2.0}
    assert first.timestamp == "2004-10-15T00:00:00Z"
    second = source.next_sample(2)
    # NaN telemetry is surfaced as None so the quality layer degrades the row honestly.
    assert second.channel_values["a"] is None


def test_replay_source_wraps_with_monotonic_clock() -> None:
    source = ReplayTelemetrySource(("a", "b"), _replay_frame())
    stamps = [source.next_sample(i).timestamp for i in range(1, 5)]
    parsed = pd.to_datetime(stamps, utc=True)
    assert parsed.is_monotonic_increasing


def test_replay_source_disables_scenario_selection() -> None:
    source = ReplayTelemetrySource(("a", "b"), _replay_frame())
    assert source.available_scenarios == []
    try:
        source.select("thermal_rise")
    except ValueError:
        return
    raise AssertionError("recorded replay must reject synthetic scenario selection")


def test_replay_injection_overlays_labelled_excursion() -> None:
    source = ReplayTelemetrySource(("a", "b"), _replay_frame())
    source.inject()
    sample = source.next_sample(1)
    assert source.scenario == "injected_demonstration_excursion"
    # The injected value overshoots the channel's observed range (kept in-bounds by the widened
    # envelope) so it is a clear, labelled demonstration excursion the detector responds to.
    injected = sample.channel_values[source._injection_channel]
    assert injected is not None
    assert injected > source._injection_high or injected < source._injection_low


def test_degenerate_guard_can_be_disabled() -> None:
    detector = CausalZScoreDetector(
        ("a",), window=5, minimum_threshold=3.0, degenerate_guard=False
    )
    detector.fit(np.full((5, 1), 4.2))
    detector.calibrate(np.full((5, 1), 4.2))
    result = detector.score_one(np.array([9.9]), update_reference=False)
    # With the guard off, the degenerate-window step is not forced anomalous (base z == 0).
    assert result.anomaly is False
    assert result.detector_evidence["degenerate_reference_window"] is False


def test_build_dataset_requires_pandas_reachable() -> None:
    # Guard against accidental import breakage of the public builder surface.
    assert callable(build_dataset)
