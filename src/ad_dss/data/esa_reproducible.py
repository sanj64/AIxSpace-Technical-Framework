"""Verified ESA dataset utilities for reproducible AD-DSS runs."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

ZENODO_RECORD = "12528696"
FORBIDDEN_TRAINING_NAMES = {
    "segments_clean.csv",
    "segments_clean (3).csv",
    "dataset_clean.csv",
}
ESA_MISSION_LAYOUT = {
    "ESA-M1": {
        "folder": Path("data/raw/ESA-M1/ESA-M1(preprocessed)"),
        "required": {
            "channels_cleaned.csv",
            "labels_cleaned.csv",
            "telecommands_cleaned.csv",
            "anomaly_types_cleaned.csv",
        },
    },
    "ESA-M2": {
        "folder": Path("data/raw/ESA-M2/ESA-M2(preprocessed)"),
        "required": {
            "channels_cleaned.csv",
            "labels_cleaned.csv",
            "telecommands_cleaned.csv",
            "events_cleaned.csv",
            "anomaly_types_cleaned.csv",
        },
    },
    "ESA-M3": {
        "folder": Path("data/raw/ESA-M3/ESA- M3(preprocessed)"),
        "required": {
            "channels_cleaned.csv",
            "labels_cleaned.csv",
            "anomaly_types_cleaned.csv",
        },
    },
}


class ReproducibilityError(ValueError):
    """Raised when a reproducible rebuild prerequisite fails."""


@dataclass(frozen=True)
class FileEvidence:
    path: str
    sha256: str
    size_bytes: int
    rows: int | None
    columns: list[str]


@dataclass(frozen=True)
class SplitBoundaries:
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str
    test_start: str
    test_end: str


@dataclass(frozen=True)
class RebuildManifest:
    zenodo_record: str
    source_files: list[FileEvidence]
    split_boundaries: SplitBoundaries | None
    scaler_fit_partition: str
    seed: int
    generated_outputs: dict[str, str]
    limitations: list[str]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_csv(path: Path) -> FileEvidence:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        columns = next(reader, [])
        rows = sum(1 for _ in reader)
    return FileEvidence(
        path=path.as_posix(),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        rows=rows,
        columns=columns,
    )


def reject_forbidden_training_input(path: str | Path) -> None:
    resolved = Path(path)
    parts = {part.lower() for part in resolved.parts}
    if resolved.name in FORBIDDEN_TRAINING_NAMES and "archive" not in parts and "tests" not in parts:
        raise ReproducibilityError(
            f"{resolved.name} is an archived, unverified input and cannot be used for active training"
        )


def validate_esa_layout(root: Path) -> list[FileEvidence]:
    evidence: list[FileEvidence] = []
    for mission, layout in ESA_MISSION_LAYOUT.items():
        folder = root / layout["folder"]
        missing = sorted(name for name in layout["required"] if not (folder / name).exists())
        if missing:
            raise ReproducibilityError(f"{mission} is missing required ESA files: {missing}")
        for name in sorted(layout["required"]):
            evidence.append(inspect_csv(folder / name))
    return evidence


def verify_archives(root: Path) -> list[FileEvidence]:
    archives = [
        root / "AI-FP" / "ESA-M1(preprocessed).zip",
        root / "AI-FP" / "ESA-M2(preprocessed).zip",
        root / "AI-FP" / "ESA- M3(preprocessed).zip",
    ]
    evidence: list[FileEvidence] = []
    for archive in archives:
        if not archive.exists():
            raise ReproducibilityError(f"ESA archive not found: {archive}")
        with zipfile.ZipFile(archive) as zipped:
            bad_member = zipped.testzip()
            if bad_member is not None:
                raise ReproducibilityError(f"{archive.name} failed zip CRC at {bad_member}")
        evidence.append(
            FileEvidence(
                path=archive.as_posix(),
                sha256=sha256_file(archive),
                size_bytes=archive.stat().st_size,
                rows=None,
                columns=[],
            )
        )
    return evidence


def compare_unverified_inputs(root: Path) -> dict[str, dict[str, str | bool]]:
    pairs = {
        "segments_clean": (
            root / "archive/unverified_pipeline/AI-FP_segments_clean (3).csv",
            root / "archive/unverified_pipeline/data_raw_segments_clean.csv",
        ),
        "dataset_clean": (
            root / "archive/unverified_pipeline/AI-FP_dataset_clean.csv",
            root / "archive/unverified_pipeline/data_raw_dataset_clean.csv",
        ),
    }
    result: dict[str, dict[str, str | bool]] = {}
    for name, (left, right) in pairs.items():
        result[name] = {
            "left": left.as_posix(),
            "right": right.as_posix(),
            "left_sha256": sha256_file(left) if left.exists() else "missing",
            "right_sha256": sha256_file(right) if right.exists() else "missing",
            "exact_copy": left.exists() and right.exists() and sha256_file(left) == sha256_file(right),
        }
    return result


def chronological_split(
    frame: pd.DataFrame,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, SplitBoundaries]:
    if not frame.index.is_monotonic_increasing:
        frame = frame.sort_index()
    if frame.index.has_duplicates:
        raise ReproducibilityError("timestamp index contains duplicates")
    if len(frame) < 5:
        raise ReproducibilityError("not enough rows for train/validation/test split")
    train_end = int(len(frame) * train_fraction)
    validation_end = train_end + int(len(frame) * validation_fraction)
    if train_end <= 0 or validation_end <= train_end or validation_end >= len(frame):
        raise ReproducibilityError("invalid split fractions")
    train = frame.iloc[:train_end].copy()
    validation = frame.iloc[train_end:validation_end].copy()
    test = frame.iloc[validation_end:].copy()
    boundaries = SplitBoundaries(
        train_start=str(train.index[0]),
        train_end=str(train.index[-1]),
        validation_start=str(validation.index[0]),
        validation_end=str(validation.index[-1]),
        test_start=str(test.index[0]),
        test_end=str(test.index[-1]),
    )
    return train, validation, test, boundaries


def fit_train_only_scaler(
    train: pd.DataFrame, validation: pd.DataFrame, test: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, StandardScaler]:
    scaler = StandardScaler()
    train_values = scaler.fit_transform(train.to_numpy(dtype=float))
    validation_values = scaler.transform(validation.to_numpy(dtype=float))
    test_values = scaler.transform(test.to_numpy(dtype=float))
    return (
        pd.DataFrame(train_values, index=train.index, columns=train.columns),
        pd.DataFrame(validation_values, index=validation.index, columns=validation.columns),
        pd.DataFrame(test_values, index=test.index, columns=test.columns),
        scaler,
    )


def assert_no_duplicate_windows(windows: np.ndarray) -> None:
    if windows.size == 0:
        raise ReproducibilityError("window array is empty")
    flattened = np.ascontiguousarray(windows.reshape(windows.shape[0], -1))
    unique = np.unique(flattened, axis=0)
    if len(unique) != len(flattened):
        raise ReproducibilityError("duplicate windows detected")


def hash_outputs(paths: Iterable[Path]) -> dict[str, str]:
    return {path.as_posix(): sha256_file(path) for path in paths if path.exists()}


def read_mission1_table(source_zip: Path, member: str) -> pd.DataFrame:
    with zipfile.ZipFile(source_zip) as outer:
        return pd.read_csv(io.BytesIO(outer.read(f"ESA-Mission1/{member}")))


def read_mission1_channel(source_zip: Path, channel: str) -> pd.Series:
    with zipfile.ZipFile(source_zip) as outer:
        payload = outer.read(f"ESA-Mission1/channels/{channel}.zip")
    with zipfile.ZipFile(io.BytesIO(payload)) as inner:
        frame = pd.read_pickle(io.BytesIO(inner.read(channel)))
    if not isinstance(frame, pd.DataFrame) or channel not in frame.columns:
        raise ReproducibilityError(f"{channel} payload is not a DataFrame with expected column")
    series = frame[channel].astype("float64").sort_index()
    series.index = pd.to_datetime(series.index)
    return series


def label_intervals(labels: pd.DataFrame, anomaly_types: pd.DataFrame, channel: str) -> pd.DataFrame:
    categories = anomaly_types[["ID", "Category"]].drop_duplicates()
    joined = labels.merge(categories, on="ID", how="left")
    channel_labels = joined[joined["Channel"] == channel].copy()
    channel_labels["StartTime"] = (
        pd.to_datetime(channel_labels["StartTime"], utc=True).dt.tz_convert(None)
    )
    channel_labels["EndTime"] = pd.to_datetime(channel_labels["EndTime"], utc=True).dt.tz_convert(
        None
    )
    return channel_labels.sort_values("StartTime")


def interval_mask(index: pd.DatetimeIndex, intervals: pd.DataFrame) -> np.ndarray:
    mask = np.zeros(len(index), dtype=bool)
    if intervals.empty:
        return mask
    values = index.to_numpy(dtype="datetime64[ns]")
    starts = intervals["StartTime"].to_numpy(dtype="datetime64[ns]")
    ends = intervals["EndTime"].to_numpy(dtype="datetime64[ns]")
    left = np.searchsorted(values, starts, side="left")
    right = np.searchsorted(values, ends, side="right")
    for start, end in zip(left, right):
        if end > start:
            mask[start:end] = True
    return mask


def zscore_scores(values: np.ndarray, mean: float, std: float, epsilon: float = 1e-9) -> np.ndarray:
    deviation = np.abs(values - mean)
    if std <= epsilon:
        return np.where(deviation <= epsilon, 0.0, np.inf)
    return deviation / std


def binary_metrics(y_true: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, float | int]:
    finite_scores = np.where(np.isfinite(scores), scores, threshold + 1.0)
    y_pred = finite_scores > threshold
    tp = int(np.sum(y_pred & y_true))
    fp = int(np.sum(y_pred & ~y_true))
    tn = int(np.sum(~y_pred & ~y_true))
    fn = int(np.sum(~y_pred & y_true))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    f05 = (1.25 * precision * recall / (0.25 * precision + recall)) if precision + recall else 0.0
    try:
        roc_auc = float(roc_auc_score(y_true, finite_scores)) if len(np.unique(y_true)) > 1 else float("nan")
    except ValueError:
        roc_auc = float("nan")
    try:
        pr_auc = (
            float(average_precision_score(y_true, finite_scores))
            if len(np.unique(y_true)) > 1
            else float("nan")
        )
    except ValueError:
        pr_auc = float("nan")
    return {
        "samples": int(len(y_true)),
        "positive_samples": int(np.sum(y_true)),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "f0_5": f05,
        "roc_auc": roc_auc,
        "pr_auc": pr_auc,
    }


def _safe_rate(count: int, samples: int) -> float:
    return float(count / samples) if samples else 0.0


def _deterministic_cap(frame: pd.DataFrame, labels: np.ndarray, cap: int) -> tuple[pd.DataFrame, np.ndarray]:
    if len(frame) <= cap:
        return frame, labels
    positions = np.linspace(0, len(frame) - 1, cap, dtype=int)
    return frame.iloc[positions].copy(), labels[positions]


def _xgboost_features(series: pd.Series) -> pd.DataFrame:
    values = series.astype("float64")
    prior = values.shift(1)
    rolling_mean = prior.rolling(24, min_periods=4).mean()
    rolling_std = prior.rolling(24, min_periods=4).std().replace(0, np.nan)
    return pd.DataFrame(
        {
            "value": values,
            "delta_1": values.diff(),
            "rolling_mean_24": rolling_mean,
            "rolling_std_24": rolling_std,
            "rolling_margin_24": values - rolling_mean,
            "rolling_abs_z_24": ((values - rolling_mean) / rolling_std).abs(),
        },
        index=series.index,
    )


def _fit_fill_values(train_features: pd.DataFrame) -> dict[str, float]:
    fill_values: dict[str, float] = {}
    for column in train_features.columns:
        finite = train_features[column].replace([np.inf, -np.inf], np.nan).dropna()
        fill_values[column] = float(finite.median()) if not finite.empty else 0.0
    return fill_values


def _prepare_features(features: pd.DataFrame, fill_values: dict[str, float]) -> pd.DataFrame:
    prepared = features.replace([np.inf, -np.inf], np.nan)
    return prepared.fillna(fill_values)


def _best_f05_threshold(labels: np.ndarray, scores: np.ndarray) -> float:
    if len(scores) == 0:
        return 0.5
    candidates = np.unique(np.quantile(scores, np.linspace(0.05, 0.95, 19)))
    if len(candidates) == 0:
        return 0.5
    best_threshold = float(candidates[0])
    best_f05 = -1.0
    for threshold in candidates:
        metrics = binary_metrics(labels.astype(bool), scores, float(threshold))
        score = float(metrics["f0_5"])
        if score > best_f05:
            best_f05 = score
            best_threshold = float(threshold)
    return best_threshold


def _window_matrix(
    values: np.ndarray,
    labels: np.ndarray,
    window_size: int,
    max_windows: int,
) -> tuple[np.ndarray, np.ndarray]:
    finite = np.isfinite(values)
    if len(values) < window_size:
        return np.empty((0, window_size, 1), dtype="float32"), np.empty((0,), dtype=bool)
    valid_positions: list[int] = []
    window_labels: list[bool] = []
    for end in range(window_size, len(values) + 1):
        start = end - window_size
        if not bool(np.all(finite[start:end])):
            continue
        valid_positions.append(start)
        window_labels.append(bool(np.any(labels[start:end])))
    if not valid_positions:
        return np.empty((0, window_size, 1), dtype="float32"), np.empty((0,), dtype=bool)
    if len(valid_positions) > max_windows:
        selected = np.linspace(0, len(valid_positions) - 1, max_windows, dtype=int)
        valid_positions = [valid_positions[index] for index in selected]
        window_labels = [window_labels[index] for index in selected]
    windows = np.empty((len(valid_positions), window_size, 1), dtype="float32")
    for output_index, start in enumerate(valid_positions):
        windows[output_index, :, 0] = values[start : start + window_size]
    return windows, np.asarray(window_labels, dtype=bool)


def _reconstruction_errors(model: object, windows: np.ndarray) -> np.ndarray:
    reconstructed = model.predict(windows, verbose=0)
    return np.mean((windows - reconstructed) ** 2, axis=(1, 2))


def train_mission1_xgboost_candidate(
    source_zip: Path,
    output_dir: Path,
    channel_limit: int | None = None,
    seed: int = 42,
    max_rows_per_partition: int = 250_000,
) -> dict[str, Path]:
    """Train an explicitly research-gated XGBoost candidate on leakage-safe features."""
    try:
        from xgboost import XGBClassifier
    except ImportError as exc:  # pragma: no cover - depends on optional local environment
        raise ReproducibilityError(
            "XGBoost candidate training requires the optional xgboost package. "
            "Install the research extra before running this command."
        ) from exc

    if not source_zip.exists():
        raise ReproducibilityError(f"ESA Mission 1 zip not found: {source_zip}")
    output_dir.mkdir(parents=True, exist_ok=True)
    channels = read_mission1_table(source_zip, "channels.csv")
    labels = read_mission1_table(source_zip, "labels.csv")
    anomaly_types = read_mission1_table(source_zip, "anomaly_types.csv")
    selected_channels = channels["Channel"].tolist()
    if channel_limit is not None:
        selected_channels = selected_channels[:channel_limit]

    channel_rows: list[dict[str, object]] = []
    attribution_rows: list[dict[str, object]] = []
    aggregate_counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "samples": 0, "positive_samples": 0}
    artifact_channels: dict[str, dict[str, object]] = {}

    for ordinal, channel in enumerate(selected_channels, start=1):
        print(f"[{ordinal}/{len(selected_channels)}] xgboost loading {channel}", flush=True)
        series = read_mission1_channel(source_zip, channel)
        finite_mask = np.isfinite(series.to_numpy(dtype=float))
        intervals = label_intervals(labels, anomaly_types, channel)
        labelled_mask = interval_mask(series.index, intervals)
        n_samples = len(series)
        train_end_pos = int(n_samples * 0.6)
        validation_end_pos = train_end_pos + int(n_samples * 0.2)
        if train_end_pos <= 0 or validation_end_pos <= train_end_pos or validation_end_pos >= n_samples:
            raise ReproducibilityError(f"{channel} does not have enough samples for splitting")
        train_mask = np.zeros(n_samples, dtype=bool)
        validation_mask = np.zeros(n_samples, dtype=bool)
        test_mask = np.zeros(n_samples, dtype=bool)
        train_mask[:train_end_pos] = True
        validation_mask[train_end_pos:validation_end_pos] = True
        test_mask[validation_end_pos:] = True

        features = _xgboost_features(series)
        fill_values = _fit_fill_values(features.loc[train_mask & finite_mask])
        prepared = _prepare_features(features, fill_values)
        train_frame = prepared.loc[train_mask & finite_mask]
        train_labels = labelled_mask[train_mask & finite_mask].astype(int)
        validation_frame = prepared.loc[validation_mask & finite_mask]
        validation_labels = labelled_mask[validation_mask & finite_mask].astype(int)
        test_frame = prepared.loc[test_mask & finite_mask]
        test_labels = labelled_mask[test_mask & finite_mask].astype(bool)

        if len(np.unique(train_labels)) < 2:
            channel_rows.append(
                {
                    "channel": channel,
                    "status": "skipped_no_positive_or_negative_training_class",
                    "samples": int(n_samples),
                }
            )
            continue

        train_frame, train_labels = _deterministic_cap(
            train_frame, train_labels, max_rows_per_partition
        )
        validation_frame, validation_labels = _deterministic_cap(
            validation_frame, validation_labels, max_rows_per_partition
        )
        test_frame, test_labels_int = _deterministic_cap(
            test_frame, test_labels.astype(int), max_rows_per_partition
        )
        test_labels = test_labels_int.astype(bool)

        positive = int(np.sum(train_labels))
        negative = int(len(train_labels) - positive)
        classifier = XGBClassifier(
            n_estimators=80,
            max_depth=3,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=seed,
            n_jobs=1,
            scale_pos_weight=(negative / positive if positive else 1.0),
        )
        classifier.fit(train_frame, train_labels)
        validation_scores = classifier.predict_proba(validation_frame)[:, 1]
        threshold = _best_f05_threshold(validation_labels.astype(bool), validation_scores)
        test_scores = classifier.predict_proba(test_frame)[:, 1]
        sample_metrics = binary_metrics(test_labels, test_scores, threshold)
        for key in aggregate_counts:
            aggregate_counts[key] += int(sample_metrics.get(key, 0))

        importances = classifier.feature_importances_
        for feature, importance in zip(train_frame.columns, importances):
            attribution_rows.append(
                {
                    "channel": channel,
                    "feature": feature,
                    "importance": float(importance),
                    "interpretation": "model feature importance; non-causal",
                }
            )
        channel_rows.append(
            {
                "channel": channel,
                "status": "research_candidate",
                "train_samples": int(len(train_frame)),
                "validation_samples": int(len(validation_frame)),
                "test_samples": int(sample_metrics["samples"]),
                "test_positive_samples": int(sample_metrics["positive_samples"]),
                "threshold": threshold,
                "precision": sample_metrics["precision"],
                "recall": sample_metrics["recall"],
                "f1": sample_metrics["f1"],
                "f0_5": sample_metrics["f0_5"],
                "roc_auc": sample_metrics["roc_auc"],
                "pr_auc": sample_metrics["pr_auc"],
                "false_alarms_per_sample": _safe_rate(int(sample_metrics["fp"]), int(sample_metrics["samples"])),
            }
        )
        artifact_channels[channel] = {
            "features": list(train_frame.columns),
            "threshold": threshold,
            "fill_values_fit_on": "chronological training partition only",
            "fill_values": fill_values,
            "max_rows_per_partition": max_rows_per_partition,
        }
        print(
            f"[{ordinal}/{len(selected_channels)}] xgboost complete {channel}: "
            f"precision={float(sample_metrics['precision']):.4f} "
            f"recall={float(sample_metrics['recall']):.4f}",
            flush=True,
        )

    precision = aggregate_counts["tp"] / (aggregate_counts["tp"] + aggregate_counts["fp"]) if aggregate_counts["tp"] + aggregate_counts["fp"] else 0.0
    recall = aggregate_counts["tp"] / (aggregate_counts["tp"] + aggregate_counts["fn"]) if aggregate_counts["tp"] + aggregate_counts["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    f05 = (1.25 * precision * recall / (0.25 * precision + recall)) if precision + recall else 0.0

    artifact = {
        "model": "mission1_xgboost_research_candidate",
        "status": "RESEARCH_GATED_NOT_ACTIVE_V0_9",
        "zenodo_record": ZENODO_RECORD,
        "source_zip_sha256": sha256_file(source_zip),
        "seed": seed,
        "candidate_limitations": [
            "Feature importances are model sensitivity evidence, not causal explanations.",
            "This candidate is not an active commercial detector unless release gates approve it.",
            "Rows may be deterministically capped per partition for reproducible local evaluation.",
        ],
        "channels": artifact_channels,
    }
    artifact_path = output_dir / "mission1_xgboost_candidate.json"
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

    channel_metrics_path = output_dir / "mission1_xgboost_channel_metrics.csv"
    pd.DataFrame(channel_rows).to_csv(channel_metrics_path, index=False)
    attribution_path = output_dir / "mission1_xgboost_feature_attributions.csv"
    pd.DataFrame(attribution_rows).to_csv(attribution_path, index=False)
    metrics = {
        "model": "mission1_xgboost_research_candidate",
        "active_training_performed": False,
        "research_candidate_trained": True,
        "status": "RESEARCH_GATED_NOT_ACTIVE_V0_9",
        "channels_attempted": len(selected_channels),
        "channels_trained": len(artifact_channels),
        "samples": aggregate_counts["samples"],
        "positive_samples": aggregate_counts["positive_samples"],
        "tp": aggregate_counts["tp"],
        "fp": aggregate_counts["fp"],
        "tn": aggregate_counts["tn"],
        "fn": aggregate_counts["fn"],
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "f0_5": f05,
        "false_alarms_per_sample": _safe_rate(aggregate_counts["fp"], aggregate_counts["samples"]),
        "source_zip_sha256": artifact["source_zip_sha256"],
        "artifact_sha256": sha256_file(artifact_path),
    }
    metrics_path = output_dir / "mission1_xgboost_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "artifact": artifact_path,
        "metrics": metrics_path,
        "channel_metrics": channel_metrics_path,
        "feature_attributions": attribution_path,
    }


def train_mission1_isolation_forest_candidate(
    source_zip: Path,
    output_dir: Path,
    channel_limit: int | None = None,
    seed: int = 42,
    max_rows_per_partition: int = 250_000,
    sensitivity_rows: int = 5_000,
) -> dict[str, Path]:
    """Train a research-gated Isolation Forest candidate on normal-only training data."""
    try:
        import joblib
        from sklearn.ensemble import IsolationForest
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise ReproducibilityError(
            "Isolation Forest candidate training requires scikit-learn and joblib."
        ) from exc

    if not source_zip.exists():
        raise ReproducibilityError(f"ESA Mission 1 zip not found: {source_zip}")
    output_dir.mkdir(parents=True, exist_ok=True)
    model_dir = output_dir / "local_model_binaries"
    model_dir.mkdir(parents=True, exist_ok=True)

    channels = read_mission1_table(source_zip, "channels.csv")
    labels = read_mission1_table(source_zip, "labels.csv")
    anomaly_types = read_mission1_table(source_zip, "anomaly_types.csv")
    selected_channels = channels["Channel"].tolist()
    if channel_limit is not None:
        selected_channels = selected_channels[:channel_limit]

    channel_rows: list[dict[str, object]] = []
    sensitivity_rows_out: list[dict[str, object]] = []
    aggregate_counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "samples": 0, "positive_samples": 0}
    artifact_channels: dict[str, dict[str, object]] = {}

    for ordinal, channel in enumerate(selected_channels, start=1):
        print(
            f"[{ordinal}/{len(selected_channels)}] isolation forest loading {channel}",
            flush=True,
        )
        series = read_mission1_channel(source_zip, channel)
        finite_mask = np.isfinite(series.to_numpy(dtype=float))
        intervals = label_intervals(labels, anomaly_types, channel)
        labelled_mask = interval_mask(series.index, intervals)
        n_samples = len(series)
        train_end_pos = int(n_samples * 0.6)
        calibration_end_pos = train_end_pos + int(n_samples * 0.2)
        if train_end_pos <= 0 or calibration_end_pos <= train_end_pos or calibration_end_pos >= n_samples:
            raise ReproducibilityError(f"{channel} does not have enough samples for splitting")
        train_mask = np.zeros(n_samples, dtype=bool)
        calibration_mask = np.zeros(n_samples, dtype=bool)
        test_mask = np.zeros(n_samples, dtype=bool)
        train_mask[:train_end_pos] = True
        calibration_mask[train_end_pos:calibration_end_pos] = True
        test_mask[calibration_end_pos:] = True

        features = _xgboost_features(series)
        normal_train_mask = train_mask & finite_mask & ~labelled_mask
        normal_calibration_mask = calibration_mask & finite_mask & ~labelled_mask
        test_finite_mask = test_mask & finite_mask
        if not np.any(normal_train_mask):
            channel_rows.append(
                {
                    "channel": channel,
                    "status": "skipped_no_normal_training_values",
                    "samples": int(n_samples),
                }
            )
            continue

        fill_values = _fit_fill_values(features.loc[normal_train_mask])
        prepared = _prepare_features(features, fill_values)
        train_frame = prepared.loc[normal_train_mask]
        calibration_frame = prepared.loc[normal_calibration_mask]
        test_frame = prepared.loc[test_finite_mask]
        test_labels = labelled_mask[test_finite_mask].astype(bool)
        if len(train_frame) < 10 or len(calibration_frame) == 0 or len(test_frame) == 0:
            channel_rows.append(
                {
                    "channel": channel,
                    "status": "skipped_empty_partition",
                    "samples": int(n_samples),
                    "train_normal_samples": int(len(train_frame)),
                    "calibration_normal_samples": int(len(calibration_frame)),
                    "test_samples": int(len(test_frame)),
                }
            )
            continue

        train_frame, _ = _deterministic_cap(
            train_frame,
            np.zeros(len(train_frame), dtype=int),
            max_rows_per_partition,
        )
        calibration_frame, _ = _deterministic_cap(
            calibration_frame,
            np.zeros(len(calibration_frame), dtype=int),
            max_rows_per_partition,
        )
        test_frame, test_labels_int = _deterministic_cap(
            test_frame,
            test_labels.astype(int),
            max_rows_per_partition,
        )
        test_labels = test_labels_int.astype(bool)

        model = IsolationForest(
            n_estimators=100,
            contamination=0.05,
            random_state=seed,
            n_jobs=1,
        )
        model.fit(train_frame)
        calibration_scores = -model.decision_function(calibration_frame)
        threshold = float(max(np.quantile(calibration_scores, 0.995), 1e-9))
        test_scores = -model.decision_function(test_frame)
        sample_metrics = binary_metrics(test_labels, test_scores, threshold)
        for key in aggregate_counts:
            aggregate_counts[key] += int(sample_metrics.get(key, 0))

        model_path = model_dir / f"{channel}.joblib"
        joblib.dump(model, model_path)
        model_hash = sha256_file(model_path)

        if len(test_frame) > sensitivity_rows:
            sensitivity_positions = np.linspace(
                0, len(test_frame) - 1, sensitivity_rows, dtype=int
            )
            sensitivity_frame = test_frame.iloc[sensitivity_positions].copy()
        else:
            sensitivity_frame = test_frame.copy()
        baseline_scores = -model.decision_function(sensitivity_frame)
        for feature in sensitivity_frame.columns:
            replaced = sensitivity_frame.copy()
            reference_value = fill_values[feature]
            replaced[feature] = reference_value
            replacement_scores = -model.decision_function(replaced)
            sensitivity_rows_out.append(
                {
                    "channel": channel,
                    "feature": feature,
                    "reference_value": reference_value,
                    "mean_abs_score_delta": float(
                        np.mean(np.abs(baseline_scores - replacement_scores))
                    ),
                    "max_abs_score_delta": float(
                        np.max(np.abs(baseline_scores - replacement_scores))
                    ),
                    "rows_evaluated": int(len(sensitivity_frame)),
                    "interpretation": "model sensitivity evidence; non-causal",
                }
            )

        training_min = {column: float(train_frame[column].min()) for column in train_frame.columns}
        training_max = {column: float(train_frame[column].max()) for column in train_frame.columns}
        channel_rows.append(
            {
                "channel": channel,
                "status": "research_candidate",
                "samples": int(n_samples),
                "train_normal_samples": int(len(train_frame)),
                "calibration_normal_samples": int(len(calibration_frame)),
                "test_samples": int(sample_metrics["samples"]),
                "test_positive_samples": int(sample_metrics["positive_samples"]),
                "threshold": threshold,
                "score_mean": float(np.mean(test_scores)) if len(test_scores) else 0.0,
                "score_max": float(np.max(test_scores)) if len(test_scores) else 0.0,
                "margin_mean": float(np.mean(test_scores - threshold)) if len(test_scores) else 0.0,
                "precision": sample_metrics["precision"],
                "recall": sample_metrics["recall"],
                "f1": sample_metrics["f1"],
                "f0_5": sample_metrics["f0_5"],
                "roc_auc": sample_metrics["roc_auc"],
                "pr_auc": sample_metrics["pr_auc"],
                "false_alarms_per_sample": _safe_rate(
                    int(sample_metrics["fp"]), int(sample_metrics["samples"])
                ),
                "local_model_path": model_path.as_posix(),
                "local_model_sha256": model_hash,
            }
        )
        artifact_channels[channel] = {
            "status": "research_candidate",
            "features": list(train_frame.columns),
            "threshold": threshold,
            "fill_values_fit_on": "finite non-labelled chronological training partition",
            "fill_values": fill_values,
            "training_feature_min": training_min,
            "training_feature_max": training_max,
            "local_model_path": model_path.as_posix(),
            "local_model_sha256": model_hash,
            "max_rows_per_partition": max_rows_per_partition,
        }
        print(
            f"[{ordinal}/{len(selected_channels)}] isolation forest complete {channel}: "
            f"precision={float(sample_metrics['precision']):.4f} "
            f"recall={float(sample_metrics['recall']):.4f}",
            flush=True,
        )

    precision = aggregate_counts["tp"] / (aggregate_counts["tp"] + aggregate_counts["fp"]) if aggregate_counts["tp"] + aggregate_counts["fp"] else 0.0
    recall = aggregate_counts["tp"] / (aggregate_counts["tp"] + aggregate_counts["fn"]) if aggregate_counts["tp"] + aggregate_counts["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    f05 = (1.25 * precision * recall / (0.25 * precision + recall)) if precision + recall else 0.0
    artifact = {
        "model": "mission1_isolation_forest_research_candidate",
        "status": "RESEARCH_GATED_NOT_ACTIVE_V0_9",
        "zenodo_record": ZENODO_RECORD,
        "source_zip_sha256": sha256_file(source_zip),
        "seed": seed,
        "n_estimators": 100,
        "contamination": 0.05,
        "candidate_limitations": [
            "Feature sensitivity is model evidence, not causation.",
            "Scores are not probabilities, confidence, certainty, or flight validation.",
            "Binary joblib models remain local and are referenced by hash in this manifest.",
        ],
        "channels": artifact_channels,
    }
    artifact_path = output_dir / "mission1_isolation_forest_candidate.json"
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    channel_metrics_path = output_dir / "mission1_isolation_forest_channel_metrics.csv"
    pd.DataFrame(channel_rows).to_csv(channel_metrics_path, index=False)
    sensitivity_path = output_dir / "mission1_isolation_forest_feature_sensitivity.csv"
    pd.DataFrame(sensitivity_rows_out).to_csv(sensitivity_path, index=False)
    metrics = {
        "model": "mission1_isolation_forest_research_candidate",
        "active_training_performed": False,
        "research_candidate_trained": True,
        "status": "RESEARCH_GATED_NOT_ACTIVE_V0_9",
        "channels_attempted": len(selected_channels),
        "channels_trained": len(artifact_channels),
        "samples": aggregate_counts["samples"],
        "positive_samples": aggregate_counts["positive_samples"],
        "tp": aggregate_counts["tp"],
        "fp": aggregate_counts["fp"],
        "tn": aggregate_counts["tn"],
        "fn": aggregate_counts["fn"],
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "f0_5": f05,
        "false_alarms_per_sample": _safe_rate(aggregate_counts["fp"], aggregate_counts["samples"]),
        "source_zip_sha256": artifact["source_zip_sha256"],
        "artifact_sha256": sha256_file(artifact_path),
    }
    metrics_path = output_dir / "mission1_isolation_forest_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "artifact": artifact_path,
        "metrics": metrics_path,
        "channel_metrics": channel_metrics_path,
        "feature_sensitivity": sensitivity_path,
    }


def train_mission1_lstm_candidate(
    source_zip: Path,
    output_dir: Path,
    channel_limit: int | None = None,
    seed: int = 42,
    epochs: int = 2,
    batch_size: int = 128,
    window_size: int = 32,
    max_windows_per_partition: int = 10_000,
) -> dict[str, Path]:
    """Train a research-gated LSTM autoencoder candidate with split-safe windows."""
    try:
        import tensorflow as tf
        from tensorflow.keras import layers, models
    except ImportError as exc:  # pragma: no cover - depends on optional local environment
        raise ReproducibilityError(
            "LSTM candidate training requires TensorFlow. Install the research extra before "
            "running this command."
        ) from exc

    if not source_zip.exists():
        raise ReproducibilityError(f"ESA Mission 1 zip not found: {source_zip}")
    if window_size < 4:
        raise ReproducibilityError("LSTM window size must be at least 4")
    tf.keras.utils.set_random_seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    model_dir = output_dir / "local_model_binaries"
    model_dir.mkdir(parents=True, exist_ok=True)

    channels = read_mission1_table(source_zip, "channels.csv")
    labels = read_mission1_table(source_zip, "labels.csv")
    anomaly_types = read_mission1_table(source_zip, "anomaly_types.csv")
    selected_channels = channels["Channel"].tolist()
    if channel_limit is not None:
        selected_channels = selected_channels[:channel_limit]

    progress_path = output_dir / "mission1_lstm_training_history.csv"
    progress_path.write_text(
        "channel,status,epochs,train_windows,calibration_windows,test_windows,final_loss\n",
        encoding="utf-8",
    )
    channel_rows: list[dict[str, object]] = []
    aggregate_counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "samples": 0, "positive_samples": 0}
    artifact_channels: dict[str, dict[str, object]] = {}

    for ordinal, channel in enumerate(selected_channels, start=1):
        print(f"[{ordinal}/{len(selected_channels)}] lstm loading {channel}", flush=True)
        series = read_mission1_channel(source_zip, channel)
        values = series.to_numpy(dtype=float)
        intervals = label_intervals(labels, anomaly_types, channel)
        labelled_mask = interval_mask(series.index, intervals)
        n_samples = len(series)
        train_end_pos = int(n_samples * 0.6)
        calibration_end_pos = train_end_pos + int(n_samples * 0.2)
        if train_end_pos <= window_size or calibration_end_pos <= train_end_pos or calibration_end_pos >= n_samples:
            raise ReproducibilityError(f"{channel} does not have enough samples for LSTM splitting")

        train_values_raw = values[:train_end_pos]
        train_labels_raw = labelled_mask[:train_end_pos]
        normal_train_values = train_values_raw[
            np.isfinite(train_values_raw) & ~train_labels_raw
        ]
        if len(normal_train_values) < window_size:
            channel_rows.append(
                {
                    "channel": channel,
                    "status": "skipped_no_normal_training_values",
                    "samples": int(n_samples),
                }
            )
            continue
        mean = float(np.mean(normal_train_values))
        std = float(np.std(normal_train_values, ddof=1)) if len(normal_train_values) > 1 else 0.0
        if std <= 1e-9:
            std = 1.0

        scaled = (values - mean) / std
        train_windows_all, train_window_labels = _window_matrix(
            scaled[:train_end_pos],
            labelled_mask[:train_end_pos],
            window_size,
            max_windows_per_partition,
        )
        calibration_windows_all, calibration_window_labels = _window_matrix(
            scaled[train_end_pos:calibration_end_pos],
            labelled_mask[train_end_pos:calibration_end_pos],
            window_size,
            max_windows_per_partition,
        )
        test_windows, test_window_labels = _window_matrix(
            scaled[calibration_end_pos:],
            labelled_mask[calibration_end_pos:],
            window_size,
            max_windows_per_partition,
        )
        train_windows = train_windows_all[~train_window_labels]
        calibration_windows = calibration_windows_all[~calibration_window_labels]
        if len(train_windows) == 0 or len(calibration_windows) == 0 or len(test_windows) == 0:
            channel_rows.append(
                {
                    "channel": channel,
                    "status": "skipped_empty_window_partition",
                    "samples": int(n_samples),
                    "train_windows": int(len(train_windows)),
                    "calibration_windows": int(len(calibration_windows)),
                    "test_windows": int(len(test_windows)),
                }
            )
            continue

        model = models.Sequential(
            [
                layers.Input(shape=(window_size, 1)),
                layers.LSTM(12, activation="tanh", return_sequences=False),
                layers.RepeatVector(window_size),
                layers.LSTM(12, activation="tanh", return_sequences=True),
                layers.TimeDistributed(layers.Dense(1)),
            ]
        )
        model.compile(optimizer="adam", loss="mse")
        history = model.fit(
            train_windows,
            train_windows,
            epochs=epochs,
            batch_size=batch_size,
            verbose=0,
            shuffle=False,
        )
        calibration_errors = _reconstruction_errors(model, calibration_windows)
        threshold = float(max(np.quantile(calibration_errors, 0.995), 1e-9))
        test_errors = _reconstruction_errors(model, test_windows)
        sample_metrics = binary_metrics(test_window_labels, test_errors, threshold)
        for key in aggregate_counts:
            aggregate_counts[key] += int(sample_metrics.get(key, 0))

        model_path = model_dir / f"{channel}.keras"
        model.save(model_path, include_optimizer=False)
        model_hash = sha256_file(model_path)
        final_loss = float(history.history["loss"][-1])
        channel_rows.append(
            {
                "channel": channel,
                "status": "research_candidate",
                "samples": int(n_samples),
                "train_windows": int(len(train_windows)),
                "calibration_windows": int(len(calibration_windows)),
                "test_windows": int(sample_metrics["samples"]),
                "test_positive_windows": int(sample_metrics["positive_samples"]),
                "threshold": threshold,
                "precision": sample_metrics["precision"],
                "recall": sample_metrics["recall"],
                "f1": sample_metrics["f1"],
                "f0_5": sample_metrics["f0_5"],
                "roc_auc": sample_metrics["roc_auc"],
                "pr_auc": sample_metrics["pr_auc"],
                "final_loss": final_loss,
                "local_model_path": model_path.as_posix(),
                "local_model_sha256": model_hash,
            }
        )
        artifact_channels[channel] = {
            "status": "research_candidate",
            "scaler_fit_on": "finite non-labelled samples in chronological training partition",
            "mean": mean,
            "std": std,
            "window_size": window_size,
            "threshold": threshold,
            "local_model_path": model_path.as_posix(),
            "local_model_sha256": model_hash,
            "window_policy": "windows are generated separately per partition and cannot cross split boundaries",
        }
        with progress_path.open("a", encoding="utf-8") as progress:
            progress.write(
                f"{channel},complete,{epochs},{len(train_windows)},{len(calibration_windows)},"
                f"{len(test_windows)},{final_loss}\n"
            )
        print(
            f"[{ordinal}/{len(selected_channels)}] lstm complete {channel}: "
            f"precision={float(sample_metrics['precision']):.4f} "
            f"recall={float(sample_metrics['recall']):.4f}",
            flush=True,
        )

    precision = aggregate_counts["tp"] / (aggregate_counts["tp"] + aggregate_counts["fp"]) if aggregate_counts["tp"] + aggregate_counts["fp"] else 0.0
    recall = aggregate_counts["tp"] / (aggregate_counts["tp"] + aggregate_counts["fn"]) if aggregate_counts["tp"] + aggregate_counts["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    f05 = (1.25 * precision * recall / (0.25 * precision + recall)) if precision + recall else 0.0
    artifact = {
        "model": "mission1_lstm_autoencoder_research_candidate",
        "status": "RESEARCH_GATED_NOT_ACTIVE_V0_9",
        "zenodo_record": ZENODO_RECORD,
        "source_zip_sha256": sha256_file(source_zip),
        "seed": seed,
        "epochs": epochs,
        "batch_size": batch_size,
        "window_size": window_size,
        "max_windows_per_partition": max_windows_per_partition,
        "candidate_limitations": [
            "Reconstruction error is model reconstruction evidence, not causation.",
            "Scores are not probabilities, confidence, certainty, or flight validation.",
            "Binary Keras models remain local and are referenced by hash in this manifest.",
        ],
        "channels": artifact_channels,
    }
    artifact_path = output_dir / "mission1_lstm_candidate.json"
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    channel_metrics_path = output_dir / "mission1_lstm_channel_metrics.csv"
    pd.DataFrame(channel_rows).to_csv(channel_metrics_path, index=False)
    explanation_path = output_dir / "mission1_lstm_explanation_limitations.json"
    explanation_path.write_text(
        json.dumps(
            {
                "explanation_type": "reconstruction_error_channel_autoencoder",
                "interpretation": "large reconstruction error means the model reconstructed the window poorly relative to training/calibration reference behavior",
                "not_claims": ["causation", "probability", "confidence", "certainty", "flight validation"],
                "counterfactual_limit": "nearest lower-error window is a model boundary, not operational advice",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    metrics = {
        "model": "mission1_lstm_autoencoder_research_candidate",
        "active_training_performed": False,
        "research_candidate_trained": True,
        "status": "RESEARCH_GATED_NOT_ACTIVE_V0_9",
        "channels_attempted": len(selected_channels),
        "channels_trained": len(artifact_channels),
        "samples": aggregate_counts["samples"],
        "positive_samples": aggregate_counts["positive_samples"],
        "tp": aggregate_counts["tp"],
        "fp": aggregate_counts["fp"],
        "tn": aggregate_counts["tn"],
        "fn": aggregate_counts["fn"],
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "f0_5": f05,
        "source_zip_sha256": artifact["source_zip_sha256"],
        "artifact_sha256": sha256_file(artifact_path),
    }
    metrics_path = output_dir / "mission1_lstm_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "artifact": artifact_path,
        "metrics": metrics_path,
        "channel_metrics": channel_metrics_path,
        "training_history": progress_path,
        "explanation_limitations": explanation_path,
    }


def event_metrics(
    index: pd.DatetimeIndex,
    intervals: pd.DataFrame,
    test_mask: np.ndarray,
    detections: np.ndarray,
) -> tuple[dict[str, int | float], pd.DataFrame]:
    rows: list[dict[str, object]] = []
    values = index.to_numpy(dtype="datetime64[ns]")
    test_positions = np.flatnonzero(test_mask)
    if len(test_positions) == 0:
        return {"events": 0, "detected_events": 0, "event_recall": 0.0}, pd.DataFrame(rows)
    test_start = values[test_positions[0]]
    test_end = values[test_positions[-1]]
    for row in intervals.itertuples(index=False):
        start = np.datetime64(row.StartTime)
        end = np.datetime64(row.EndTime)
        if end < test_start or start > test_end:
            continue
        left = int(np.searchsorted(values, start, side="left"))
        right = int(np.searchsorted(values, end, side="right"))
        overlap = np.zeros(len(index), dtype=bool)
        overlap[left:right] = True
        overlap &= test_mask
        detected = bool(np.any(detections & overlap))
        rows.append(
            {
                "id": row.ID,
                "channel": row.Channel,
                "category": getattr(row, "Category", "unknown"),
                "start": str(row.StartTime),
                "end": str(row.EndTime),
                "test_samples": int(np.sum(overlap)),
                "detected": detected,
            }
        )
    events = len(rows)
    detected_events = sum(1 for row in rows if bool(row["detected"]))
    return (
        {
            "events": events,
            "detected_events": detected_events,
            "event_recall": detected_events / events if events else 0.0,
        },
        pd.DataFrame(rows),
    )


def train_mission1_zscore(
    source_zip: Path,
    output_dir: Path,
    channel_limit: int | None = None,
    threshold_quantile: float = 0.995,
    minimum_threshold: float = 3.5,
    seed: int = 42,
) -> dict[str, Path]:
    if not source_zip.exists():
        raise ReproducibilityError(f"ESA Mission 1 zip not found: {source_zip}")
    output_dir.mkdir(parents=True, exist_ok=True)
    channels = read_mission1_table(source_zip, "channels.csv")
    labels = read_mission1_table(source_zip, "labels.csv")
    anomaly_types = read_mission1_table(source_zip, "anomaly_types.csv")
    selected_channels = channels["Channel"].tolist()
    if channel_limit is not None:
        selected_channels = selected_channels[:channel_limit]
    progress_path = output_dir / "mission1_training_progress.csv"
    progress_path.write_text(
        "channel,status,samples,train_normal_samples,validation_normal_samples\n",
        encoding="utf-8",
    )

    channel_rows: list[dict[str, object]] = []
    event_rows: list[pd.DataFrame] = []
    artifact_channels: dict[str, dict[str, object]] = {}
    aggregate_counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "samples": 0, "positive_samples": 0}

    for ordinal, channel in enumerate(selected_channels, start=1):
        print(f"[{ordinal}/{len(selected_channels)}] loading {channel}", flush=True)
        series = read_mission1_channel(source_zip, channel)
        finite_mask = np.isfinite(series.to_numpy(dtype=float))
        intervals = label_intervals(labels, anomaly_types, channel)
        labelled_mask = interval_mask(series.index, intervals)
        n_samples = len(series)
        train_end_pos = int(n_samples * 0.6)
        validation_end_pos = train_end_pos + int(n_samples * 0.2)
        if train_end_pos <= 0 or validation_end_pos <= train_end_pos or validation_end_pos >= n_samples:
            raise ReproducibilityError(f"{channel} does not have enough samples for splitting")
        train_mask = np.zeros(n_samples, dtype=bool)
        validation_mask = np.zeros(n_samples, dtype=bool)
        test_mask = np.zeros(n_samples, dtype=bool)
        train_mask[:train_end_pos] = True
        validation_mask[train_end_pos:validation_end_pos] = True
        test_mask[validation_end_pos:] = True
        boundaries = SplitBoundaries(
            train_start=str(series.index[0]),
            train_end=str(series.index[train_end_pos - 1]),
            validation_start=str(series.index[train_end_pos]),
            validation_end=str(series.index[validation_end_pos - 1]),
            test_start=str(series.index[validation_end_pos]),
            test_end=str(series.index[-1]),
        )
        normal_train_mask = train_mask & ~labelled_mask & finite_mask
        if not np.any(normal_train_mask):
            raise ReproducibilityError(f"{channel} has no finite normal training samples")
        train_values = series.to_numpy(dtype=float)[normal_train_mask]
        mean = float(np.mean(train_values))
        std = float(np.std(train_values, ddof=1)) if len(train_values) > 1 else 0.0
        scores = zscore_scores(series.to_numpy(dtype=float), mean, std)
        normal_validation = validation_mask & ~labelled_mask & finite_mask
        if np.any(normal_validation):
            threshold = float(max(np.quantile(scores[normal_validation], threshold_quantile), minimum_threshold))
        else:
            threshold = float(minimum_threshold)
        detections = np.where(np.isfinite(scores), scores, threshold + 1.0) > threshold
        test_finite = test_mask & finite_mask
        sample_metrics = binary_metrics(labelled_mask[test_finite], scores[test_finite], threshold)
        channel_event_metrics, channel_events = event_metrics(
            series.index, intervals, test_finite, detections
        )
        if not channel_events.empty:
            event_rows.append(channel_events)
        for key in aggregate_counts:
            aggregate_counts[key] += int(sample_metrics.get(key, 0))
        channel_rows.append(
            {
                "channel": channel,
                "samples": int(len(series)),
                "train_normal_samples": int(np.sum(normal_train_mask)),
                "validation_normal_samples": int(np.sum(normal_validation)),
                "test_samples": int(sample_metrics["samples"]),
                "test_positive_samples": int(sample_metrics["positive_samples"]),
                "mean": mean,
                "std": std,
                "threshold": threshold,
                "precision": sample_metrics["precision"],
                "recall": sample_metrics["recall"],
                "f1": sample_metrics["f1"],
                "f0_5": sample_metrics["f0_5"],
                "roc_auc": sample_metrics["roc_auc"],
                "pr_auc": sample_metrics["pr_auc"],
                "events": channel_event_metrics["events"],
                "detected_events": channel_event_metrics["detected_events"],
                "event_recall": channel_event_metrics["event_recall"],
            }
        )
        artifact_channels[channel] = {
            "mean": mean,
            "std": std,
            "threshold": threshold,
            "split_boundaries": asdict(boundaries),
            "training_policy": "normal-only chronological train partition",
        }
        with progress_path.open("a", encoding="utf-8") as progress:
            progress.write(
                f"{channel},complete,{len(series)},{int(np.sum(normal_train_mask))},"
                f"{int(np.sum(normal_validation))}\n"
            )
        print(
            f"[{ordinal}/{len(selected_channels)}] complete {channel}: "
            f"samples={len(series)} threshold={threshold:.6g} "
            f"precision={float(sample_metrics['precision']):.4f} "
            f"recall={float(sample_metrics['recall']):.4f}",
            flush=True,
        )

    precision = aggregate_counts["tp"] / (aggregate_counts["tp"] + aggregate_counts["fp"]) if aggregate_counts["tp"] + aggregate_counts["fp"] else 0.0
    recall = aggregate_counts["tp"] / (aggregate_counts["tp"] + aggregate_counts["fn"]) if aggregate_counts["tp"] + aggregate_counts["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    f05 = (1.25 * precision * recall / (0.25 * precision + recall)) if precision + recall else 0.0

    artifact = {
        "model": "mission1_channelwise_zscore",
        "zenodo_record": ZENODO_RECORD,
        "source_zip_sha256": sha256_file(source_zip),
        "source_zip_size_bytes": source_zip.stat().st_size,
        "seed": seed,
        "threshold_quantile": threshold_quantile,
        "minimum_threshold": minimum_threshold,
        "channels": artifact_channels,
    }
    artifact_path = output_dir / "mission1_zscore_model.json"
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

    channel_metrics_path = output_dir / "mission1_channel_metrics.csv"
    pd.DataFrame(channel_rows).to_csv(channel_metrics_path, index=False)
    event_metrics_path = output_dir / "mission1_event_metrics.csv"
    if event_rows:
        pd.concat(event_rows, ignore_index=True).to_csv(event_metrics_path, index=False)
    else:
        pd.DataFrame(columns=["id", "channel", "category", "start", "end", "test_samples", "detected"]).to_csv(
            event_metrics_path, index=False
        )

    metrics = {
        "model": "mission1_channelwise_zscore",
        "active_training_performed": True,
        "channels_trained": len(selected_channels),
        "samples": aggregate_counts["samples"],
        "positive_samples": aggregate_counts["positive_samples"],
        "tp": aggregate_counts["tp"],
        "fp": aggregate_counts["fp"],
        "tn": aggregate_counts["tn"],
        "fn": aggregate_counts["fn"],
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "f0_5": f05,
        "source_zip_sha256": artifact["source_zip_sha256"],
        "artifact_sha256": sha256_file(artifact_path),
    }
    metrics_path = output_dir / "mission1_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "artifact": artifact_path,
        "metrics": metrics_path,
        "channel_metrics": channel_metrics_path,
        "event_metrics": event_metrics_path,
    }
