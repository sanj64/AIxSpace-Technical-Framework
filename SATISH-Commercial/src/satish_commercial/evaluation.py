"""Chronological, event-aware telemetry evaluation metrics."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score


@dataclass(frozen=True, slots=True)
class Interval:
    start: int
    end: int


def intervals(binary: np.ndarray) -> list[Interval]:
    values = np.asarray(binary, dtype=bool)
    result: list[Interval] = []
    start: int | None = None
    for index, value in enumerate(values):
        if value and start is None:
            start = index
        if start is not None and (not value or index == len(values) - 1):
            end = index if value and index == len(values) - 1 else index - 1
            result.append(Interval(start, end))
            start = None
    return result


def _overlap(left: Interval, right: Interval) -> bool:
    return left.start <= right.end and right.start <= left.end


def _wilson(successes: int, total: int, z: float = 1.96) -> list[float] | None:
    if total == 0:
        return None
    proportion = successes / total
    denominator = 1 + (z * z / total)
    centre = (proportion + z * z / (2 * total)) / denominator
    radius = (
        z * sqrt((proportion * (1 - proportion) / total) + z * z / (4 * total**2)) / denominator
    )
    return [max(0.0, centre - radius), min(1.0, centre + radius)]


def evaluate_predictions(
    labels: np.ndarray,
    predictions: np.ndarray,
    scores: np.ndarray,
    timestamps: pd.Series,
    *,
    rare_nominal: np.ndarray | None = None,
) -> dict[str, Any]:
    truth = np.asarray(labels, dtype=bool)
    predicted = np.asarray(predictions, dtype=bool)
    numeric_scores = np.asarray(scores, dtype=float)
    if not (len(truth) == len(predicted) == len(numeric_scores) == len(timestamps)):
        raise ValueError("evaluation inputs must have equal length")
    true_events = intervals(truth)
    predicted_events = intervals(predicted)
    true_positive_events = sum(
        any(_overlap(event, candidate) for candidate in predicted_events) for event in true_events
    )
    false_negative_events = len(true_events) - true_positive_events
    false_positive_events = sum(
        not any(_overlap(event, candidate) for candidate in true_events)
        for event in predicted_events
    )
    precision = (
        true_positive_events / (true_positive_events + false_positive_events)
        if true_positive_events + false_positive_events
        else 0.0
    )
    recall = true_positive_events / len(true_events) if true_events else 0.0
    beta_squared = 0.25
    f_beta = (
        (1 + beta_squared) * precision * recall / (beta_squared * precision + recall)
        if precision + recall
        else 0.0
    )
    parsed_time = pd.to_datetime(timestamps, utc=True, errors="coerce")
    duration_hours = max(
        (parsed_time.max() - parsed_time.min()).total_seconds() / 3600.0,
        1 / 3600.0,
    )
    latency_seconds: list[float] = []
    for event in true_events:
        hits = np.flatnonzero(predicted[event.start : event.end + 1])
        if len(hits):
            hit_index = event.start + int(hits[0])
            latency_seconds.append(
                float((parsed_time.iloc[hit_index] - parsed_time.iloc[event.start]).total_seconds())
            )
    auc_pr: float | None = None
    if len(np.unique(truth)) == 2 and np.isfinite(numeric_scores).all():
        auc_pr = float(average_precision_score(truth.astype(int), numeric_scores))
    rare_overlap_count = 0
    if rare_nominal is not None:
        rare = np.asarray(rare_nominal, dtype=bool)
        rare_overlap_count = int(np.sum(predicted & rare))
    return {
        "sample_count": int(len(truth)),
        "positive_sample_count": int(truth.sum()),
        "true_event_count": len(true_events),
        "predicted_event_count": len(predicted_events),
        "true_positive_events": true_positive_events,
        "false_positive_events": false_positive_events,
        "false_negative_events": false_negative_events,
        "event_precision": precision,
        "event_precision_95pct_wilson": _wilson(
            true_positive_events, true_positive_events + false_positive_events
        ),
        "event_recall": recall,
        "event_recall_95pct_wilson": _wilson(true_positive_events, len(true_events)),
        "event_f0_5": f_beta,
        "auc_pr": auc_pr,
        "false_alarms_per_hour": false_positive_events / duration_hours,
        "onset_latency_seconds": {
            "count": len(latency_seconds),
            "median": float(np.median(latency_seconds)) if latency_seconds else None,
            "p95": float(np.quantile(latency_seconds, 0.95)) if latency_seconds else None,
        },
        "rare_nominal_prediction_overlaps": rare_overlap_count,
        "uncertainty_note": (
            "Wilson intervals cover event precision/recall only; other metrics are point estimates."
        ),
    }


def grouped_metrics(
    frame: pd.DataFrame,
    labels: np.ndarray,
    predictions: np.ndarray,
    scores: np.ndarray,
    timestamp_column: str,
    dimensions: tuple[str, ...] = ("subsystem", "mission_phase", "anomaly_type", "channel_class"),
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for dimension in dimensions:
        if dimension not in frame.columns:
            continue
        result[dimension] = {}
        for value, indexes in frame.groupby(dimension, dropna=False).groups.items():
            positions = np.asarray(list(indexes), dtype=int)
            result[dimension][str(value)] = evaluate_predictions(
                labels[positions],
                predictions[positions],
                scores[positions],
                frame.iloc[positions][timestamp_column],
            )
    return result
