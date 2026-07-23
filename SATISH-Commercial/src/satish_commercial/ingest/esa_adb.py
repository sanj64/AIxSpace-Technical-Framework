"""Causal ingestion of the ESA Anomaly Detection Benchmark (Mission1) into a SATISH frame.

The public ESA-ADB Mission1 archive stores each channel as a pickled, datetime-indexed
pandas DataFrame inside a per-channel zip, plus interval labels in ``labels.csv`` and a
``channels.csv`` subsystem map. This adapter turns a *bounded time window* of all requested
channels into the single wide, chronologically ordered frame ``run_replay`` expects
(``timestamp`` + one column per feature channel + a binary ``anomaly_label``), using only
causal alignment: every grid value is the most recent observation at or before its
timestamp, never a future one. Anomalous/degraded handling and detection remain the job of
the downstream quality/detector layers.

SATISH is advisory-only: the ``telecommands`` entries in the archive are never read here and
never become a command or actuation path. This module only produces input telemetry.

Security note: the per-channel payloads are Python pickles. Only ingest archives from a
trusted, hash-verified source (see ``scripts/download_dataset.py``).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ARCHIVE_ROOT = "ESA-Mission1"
# Default demo window: a bounded slice around labelled anomaly ``id_1``
# (2004-12-01 -> 2004-12-16, 52 channels) with clean lead-in so the anomaly falls in the
# chronological test partition of the 60/20/20 replay split.
DEFAULT_WINDOW_START = "2004-10-15T00:00:00Z"
DEFAULT_WINDOW_END = "2004-12-18T00:00:00Z"


def _member(zip_path: Path, name: str) -> bytes:
    with zipfile.ZipFile(zip_path) as outer:
        return outer.read(f"{ARCHIVE_ROOT}/{name}")


def load_channels_metadata(zip_path: Path) -> pd.DataFrame:
    """Return the ``channels.csv`` map (Channel, Subsystem, Physical Unit, Group, Target)."""

    return pd.read_csv(io.BytesIO(_member(zip_path, "channels.csv")))


def load_labels(zip_path: Path) -> pd.DataFrame:
    """Return ``labels.csv`` with parsed UTC ``StartTime``/``EndTime`` interval columns."""

    labels = pd.read_csv(io.BytesIO(_member(zip_path, "labels.csv")))
    labels["StartTime"] = pd.to_datetime(labels["StartTime"], utc=True)
    labels["EndTime"] = pd.to_datetime(labels["EndTime"], utc=True)
    return labels


def read_channel_series(
    zip_path: Path,
    channel: str,
    *,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> pd.Series:
    """Read one channel's pickled series and slice it to ``[window_start, window_end]`` (UTC).

    The series is returned sorted, de-duplicated (last value kept for duplicate timestamps),
    and UTC-indexed. Slicing happens before any heavy work so peak memory stays at roughly a
    single channel's window.
    """

    inner_bytes = _member(zip_path, f"channels/{channel}.zip")
    with zipfile.ZipFile(io.BytesIO(inner_bytes)) as inner:
        payload = inner.read(channel)
    frame = pd.read_pickle(io.BytesIO(payload))  # noqa: S301  # nosec B301 - trusted, hashed archive
    series = frame[channel] if channel in frame.columns else frame.iloc[:, 0]
    index = pd.to_datetime(series.index)
    index = index.tz_localize("UTC") if index.tz is None else index.tz_convert("UTC")
    series = pd.Series(np.asarray(series.to_numpy(), dtype=float), index=index, name=channel)
    series = series[~series.index.duplicated(keep="last")].sort_index()
    return series.loc[(series.index >= window_start) & (series.index <= window_end)]


def _causal_align(series: pd.Series, grid: pd.DatetimeIndex, max_gap_seconds: float) -> pd.Series:
    """Reindex ``series`` onto ``grid`` using the last observation at or before each point.

    ``reindex(method="ffill")`` propagates the most recent prior value forward, which is
    strictly causal. ``tolerance`` caps how stale a carried value may be; older gaps stay
    NaN so the downstream quality layer flags the row DEGRADED rather than masking a dropout.
    """

    aligned = series.reindex(grid, method="ffill", tolerance=pd.Timedelta(seconds=max_gap_seconds))
    return aligned


def _anomaly_label(
    labels: pd.DataFrame,
    grid: pd.DatetimeIndex,
    *,
    channels: tuple[str, ...],
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> np.ndarray:
    """Global-OR binary label: 1 where any channel interval covers the grid timestamp."""

    flagged: np.ndarray = np.zeros(len(grid), dtype=int)
    relevant = labels[
        labels["Channel"].isin(channels)
        & (labels["StartTime"] <= window_end)
        & (labels["EndTime"] >= window_start)
    ]
    grid_values = grid.values
    for start, end in zip(relevant["StartTime"], relevant["EndTime"], strict=True):
        left = int(np.searchsorted(grid_values, np.datetime64(start.to_datetime64()), side="left"))
        right = int(np.searchsorted(grid_values, np.datetime64(end.to_datetime64()), side="right"))
        flagged[left:right] = 1
    return flagged


def build_dataset(
    zip_path: Path,
    *,
    channels: tuple[str, ...] | None = None,
    window_start: str = DEFAULT_WINDOW_START,
    window_end: str = DEFAULT_WINDOW_END,
    freq: str = "5min",
    max_gap_seconds: float = 900.0,
    timestamp_column: str = "timestamp",
    label_column: str = "anomaly_label",
    mission_phase: str = "OPERATIONS",
) -> pd.DataFrame:
    """Build a single causal, chronologically ordered replay frame for the requested channels.

    Every requested channel is aligned onto one uniform UTC grid (``freq``) by carrying the
    last observation at or before each point (causal). Rows before a channel's first sample,
    or after a gap longer than ``max_gap_seconds``, stay NaN so the quality layer degrades
    them honestly. ``anomaly_label`` is 1 where any ``labels.csv`` interval covers the row.
    """

    start = pd.Timestamp(window_start)
    end = pd.Timestamp(window_end)
    if start.tz is None:
        start = start.tz_localize("UTC")
    if end.tz is None:
        end = end.tz_localize("UTC")

    metadata = load_channels_metadata(zip_path)
    all_channels = tuple(str(name) for name in metadata["Channel"])
    selected = channels if channels is not None else all_channels

    grid = pd.date_range(start=start, end=end, freq=freq, tz="UTC")
    columns: dict[str, np.ndarray] = {}
    for channel in selected:
        series = read_channel_series(zip_path, channel, window_start=start, window_end=end)
        columns[channel] = _causal_align(series, grid, max_gap_seconds).to_numpy(dtype=float)

    frame = pd.DataFrame(columns, index=grid)
    frame.insert(0, timestamp_column, grid.strftime("%Y-%m-%dT%H:%M:%S.%f").str.slice(0, -3) + "Z")
    frame[label_column] = _anomaly_label(
        load_labels(zip_path),
        grid,
        channels=tuple(selected),
        window_start=start,
        window_end=end,
    )
    frame["mission_phase"] = mission_phase
    return frame.reset_index(drop=True)


def derive_physical_bounds(
    frame: pd.DataFrame, features: tuple[str, ...], *, margin: float = 0.05
) -> dict[str, dict[str, float]]:
    """Observed-range envelope per channel (not a vendor/spec limit).

    Bounds are the finite observed min/max widened by a relative ``margin`` so that in-range
    telemetry (including the labelled anomaly) is scored by the detector rather than tripping
    a physical-bound DEGRADED. Channels with no finite samples get a permissive full-range
    envelope; they will still DEGRADE on the underlying NaN via the quality layer.
    """

    bounds: dict[str, dict[str, float]] = {}
    for feature in features:
        values = pd.to_numeric(frame[feature], errors="coerce").to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            bounds[feature] = {"min": -1e9, "max": 1e9}
            continue
        low = float(finite.min())
        high = float(finite.max())
        span = high - low
        pad = abs(span) * margin if span > 0 else max(abs(high), 1.0) * margin
        bounds[feature] = {"min": low - pad, "max": high + pad}
    return bounds
