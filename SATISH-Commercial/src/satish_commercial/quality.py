"""Causal, read-only telemetry quality assessment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .contracts import ConfigPackV1, SystemMode


@dataclass(slots=True)
class FrameQualityResult:
    frame: pd.DataFrame
    global_flags: tuple[str, ...]
    imputations: tuple[dict[str, object], ...]
    dropped_signals: tuple[str, ...]


@dataclass(slots=True)
class SampleQualityResult:
    row: pd.Series
    mode: SystemMode
    flags: tuple[str, ...]
    timestamp: pd.Timestamp | None


def assess_sample(
    *,
    timestamp: str,
    channel_order: tuple[str, ...],
    channel_values: dict[str, Any],
    mission_phase: str,
    config: ConfigPackV1,
    previous_timestamp: pd.Timestamp | None,
) -> SampleQualityResult:
    """Validate one live sample without repair, reordering, or future information."""

    flags: list[str] = []
    expected = tuple(config.feature_columns)
    if channel_order != expected:
        flags.append("schema_order_mismatch")
    missing = sorted(set(expected) - set(channel_values))
    unknown = sorted(set(channel_values) - set(expected))
    flags.extend(f"missing_channel:{name}" for name in missing)
    flags.extend(f"unknown_channel:{name}" for name in unknown)

    parsed = pd.to_datetime(timestamp, utc=True, errors="coerce")
    parsed_timestamp = None if pd.isna(parsed) else pd.Timestamp(parsed)
    if parsed_timestamp is None:
        flags.append("invalid_timestamp")
    elif previous_timestamp is not None:
        gap = (parsed_timestamp - previous_timestamp).total_seconds()
        if gap <= 0:
            flags.append("non_monotonic_timestamp")
        elif gap > float(config.detector_settings.get("max_gap_seconds", 300.0)):
            flags.append("stale_telemetry")

    row_values: dict[str, Any] = {
        config.timestamp_column: parsed_timestamp,
        "mission_phase": mission_phase,
    }
    for feature in expected:
        raw = channel_values.get(feature)
        try:
            numeric = float(raw) if raw is not None else float("nan")
        except (TypeError, ValueError):
            numeric = float("nan")
        if not np.isfinite(numeric):
            flags.append(f"nonfinite_value:{feature}")
        else:
            bounds = config.physical_bounds[feature]
            if numeric < bounds["min"] or numeric > bounds["max"]:
                flags.append(f"physical_bound_violation:{feature}")
        row_values[feature] = numeric

    unique_flags = tuple(sorted(set(flags)))
    return SampleQualityResult(
        row=pd.Series(row_values),
        mode=SystemMode.DEGRADED if unique_flags else SystemMode.NORMAL,
        flags=unique_flags,
        timestamp=parsed_timestamp,
    )


def assess_frame(frame: pd.DataFrame, config: ConfigPackV1) -> FrameQualityResult:
    """Return a copied, chronologically sorted frame with row-level quality state.

    No future value is ever used. A missing value may be causally forward-filled to
    allow inspection, but the affected row remains DEGRADED and cannot receive a
    recommendation other than ALERT_ONLY.
    """

    working = frame.copy(deep=True)
    required = {config.timestamp_column, *config.feature_columns}
    missing = sorted(required - set(working.columns))
    if missing:
        return FrameQualityResult(
            frame=working,
            global_flags=tuple(f"missing_channel:{item}" for item in missing),
            imputations=(),
            dropped_signals=(),
        )

    timestamps = pd.to_datetime(working[config.timestamp_column], utc=True, errors="coerce")
    invalid_timestamp = timestamps.isna()
    working[config.timestamp_column] = timestamps
    working = working.sort_values(config.timestamp_column, kind="mergesort").reset_index(drop=True)

    row_flags: list[list[str]] = [[] for _ in range(len(working))]
    if invalid_timestamp.any():
        for index in working.index[working[config.timestamp_column].isna()]:
            row_flags[int(index)].append("invalid_timestamp")

    duplicate_mask = working[config.timestamp_column].duplicated(keep=False)
    for index in working.index[duplicate_mask]:
        row_flags[int(index)].append("duplicate_timestamp")

    max_gap_seconds = float(config.detector_settings.get("max_gap_seconds", 300.0))
    gaps = working[config.timestamp_column].diff().dt.total_seconds()
    for index in working.index[gaps > max_gap_seconds]:
        row_flags[int(index)].append("stale_telemetry")

    imputations: list[dict[str, object]] = []
    for feature in config.feature_columns:
        numeric = pd.to_numeric(working[feature], errors="coerce").astype(float)
        numeric = numeric.replace([np.inf, -np.inf], np.nan)
        missing_mask = numeric.isna()
        for index in working.index[missing_mask]:
            row_flags[int(index)].append(f"nonfinite_value:{feature}")
        filled = numeric.ffill()
        for index in working.index[missing_mask & filled.notna()]:
            imputations.append(
                {"row": int(index), "feature": feature, "method": "causal_forward_fill"}
            )
        working[feature] = filled

        bounds = config.physical_bounds[feature]
        violation = (filled < bounds["min"]) | (filled > bounds["max"])
        for index in working.index[violation.fillna(False)]:
            row_flags[int(index)].append(f"physical_bound_violation:{feature}")

    working["_quality_flags"] = [tuple(sorted(set(flags))) for flags in row_flags]
    working["_system_mode"] = [
        SystemMode.DEGRADED.value if flags else SystemMode.NORMAL.value
        for flags in working["_quality_flags"]
    ]
    return FrameQualityResult(
        frame=working,
        global_flags=(),
        imputations=tuple(imputations),
        dropped_signals=(),
    )
