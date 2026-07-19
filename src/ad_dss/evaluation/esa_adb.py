"""Event-wise ESA-ADB evaluation utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class EventInterval:
    event_id: str
    start: float
    end: float
    kind: str = "anomaly"

    @property
    def normalized(self) -> tuple[float, float]:
        return (min(self.start, self.end), max(self.start, self.end))


@dataclass(frozen=True)
class EventMetrics:
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f0_5: float
    rare_nominal_overlaps: int
    rare_nominal_events: int


def intervals_overlap(left: EventInterval, right: EventInterval) -> bool:
    left_start, left_end = left.normalized
    right_start, right_end = right.normalized
    return left_start <= right_end and right_start <= left_end


def f_beta(precision: float, recall: float, beta: float = 0.5) -> float:
    if precision == 0.0 and recall == 0.0:
        return 0.0
    beta_sq = beta * beta
    return (1 + beta_sq) * precision * recall / ((beta_sq * precision) + recall)


def evaluate_events(
    predictions: list[EventInterval],
    anomaly_truth: list[EventInterval],
    rare_nominal_truth: list[EventInterval] | None = None,
) -> EventMetrics:
    """Evaluate predictions against anomaly intervals with one-to-one matching."""
    rare_nominal_truth = rare_nominal_truth or []
    matched_predictions: set[int] = set()
    true_positives = 0

    for truth in anomaly_truth:
        match_idx = next(
            (
                idx
                for idx, prediction in enumerate(predictions)
                if idx not in matched_predictions and intervals_overlap(prediction, truth)
            ),
            None,
        )
        if match_idx is not None:
            matched_predictions.add(match_idx)
            true_positives += 1

    false_positives = len(predictions) - len(matched_predictions)
    false_negatives = len(anomaly_truth) - true_positives
    precision = true_positives / (true_positives + false_positives) if predictions else 0.0
    recall = true_positives / len(anomaly_truth) if anomaly_truth else 0.0
    rare_nominal_overlaps = sum(
        1
        for rare_nominal in rare_nominal_truth
        if any(intervals_overlap(prediction, rare_nominal) for prediction in predictions)
    )
    return EventMetrics(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f0_5=f_beta(precision, recall, beta=0.5),
        rare_nominal_overlaps=rare_nominal_overlaps,
        rare_nominal_events=len(rare_nominal_truth),
    )


def metrics_row(
    *,
    dataset: str,
    model_version: str,
    configuration: str,
    metrics: EventMetrics,
) -> dict[str, str | int | float]:
    return {
        "dataset": dataset,
        "model_version": model_version,
        "configuration": configuration,
        "true_positives": metrics.true_positives,
        "false_positives": metrics.false_positives,
        "false_negatives": metrics.false_negatives,
        "precision": round(metrics.precision, 6),
        "recall": round(metrics.recall, 6),
        "event_f0_5": round(metrics.f0_5, 6),
        "rare_nominal_overlaps": metrics.rare_nominal_overlaps,
        "rare_nominal_events": metrics.rare_nominal_events,
    }


def write_metrics_csv(row: dict[str, str | int | float], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row]).to_csv(output, index=False)
    return output
