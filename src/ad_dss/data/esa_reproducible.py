"""Verified ESA dataset utilities for reproducible AD-DSS runs."""

from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
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
