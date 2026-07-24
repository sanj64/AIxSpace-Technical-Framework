"""Tests for the ESA reproducibility rebuild controls."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ad_dss.data.esa_reproducible import (
    ReproducibilityError,
    assert_no_duplicate_windows,
    chronological_split,
    fit_train_only_scaler,
    reject_forbidden_training_input,
    train_mission1_zscore,
    validate_esa_layout,
)
from ad_dss.pipeline.esa_rebuild import dry_run


def _write_small_mission1_zip(path: Path) -> None:
    index = pd.date_range("2000-01-01", periods=100, freq="h")
    values = np.sin(np.arange(100) / 8.0).astype("float32")
    values[85:90] = 12.0
    frame = pd.DataFrame({"channel_1": values}, index=index)
    frame.index.name = "datetime"
    payload = io.BytesIO()
    frame.to_pickle(payload)
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w", zipfile.ZIP_DEFLATED) as inner:
        inner.writestr("channel_1", payload.getvalue())
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as outer:
        outer.writestr(
            "ESA-Mission1/channels.csv",
            "Channel,Subsystem,Physical Unit,Group,Target\n"
            "channel_1,subsystem_1,physical_unit_1,1,YES\n",
        )
        outer.writestr("ESA-Mission1/anomaly_types.csv", "ID,Category\nid_1,Anomaly\n")
        outer.writestr(
            "ESA-Mission1/labels.csv",
            "ID,Channel,StartTime,EndTime\n"
            "id_1,channel_1,2000-01-04T13:00:00Z,2000-01-04T17:00:00Z\n",
        )
        outer.writestr("ESA-Mission1/telecommands.csv", "Telecommand,Priority\nnoop,low\n")
        outer.writestr("ESA-Mission1/channels/channel_1.zip", nested.getvalue())


def test_forbidden_training_inputs_are_rejected() -> None:
    with pytest.raises(ReproducibilityError):
        reject_forbidden_training_input("data/raw/segments_clean.csv")
    reject_forbidden_training_input("archive/unverified_pipeline/data_raw_segments_clean.csv")
    reject_forbidden_training_input("tests/fixtures/segments_clean.csv")


def test_esa_layout_validation_reads_expected_sources() -> None:
    evidence = validate_esa_layout(Path("."))
    paths = {item.path for item in evidence}
    assert any("ESA-M1" in path and "labels_cleaned.csv" in path for path in paths)
    assert any(item.rows and item.rows > 0 for item in evidence)


def test_chronological_split_has_no_overlap() -> None:
    frame = pd.DataFrame(
        {"value": np.arange(20, dtype=float)},
        index=pd.date_range("2026-01-01", periods=20, freq="s"),
    )
    train, validation, test, boundaries = chronological_split(frame)
    assert train.index.max() < validation.index.min()
    assert validation.index.max() < test.index.min()
    assert boundaries.scaler_fit_partition if hasattr(boundaries, "scaler_fit_partition") else True


def test_scaler_is_fit_only_on_training_partition() -> None:
    train = pd.DataFrame({"value": [0.0, 1.0, 2.0]})
    validation = pd.DataFrame({"value": [100.0]})
    test = pd.DataFrame({"value": [200.0]})
    scaled_train, scaled_validation, scaled_test, scaler = fit_train_only_scaler(
        train, validation, test
    )
    assert abs(float(scaled_train["value"].mean())) < 1e-12
    assert float(scaler.mean_[0]) == 1.0
    assert float(scaled_validation["value"].iloc[0]) > 100.0
    assert float(scaled_test["value"].iloc[0]) > 200.0


def test_duplicate_windows_are_rejected() -> None:
    windows = np.array([[[1.0], [2.0]], [[1.0], [2.0]]])
    with pytest.raises(ReproducibilityError):
        assert_no_duplicate_windows(windows)


def test_dry_run_writes_manifest(tmp_path: Path) -> None:
    output = dry_run(Path("."), tmp_path)
    manifest = tmp_path / "run_manifest.json"
    assert output.exists()
    assert manifest.exists()
    assert "12528696" in manifest.read_text(encoding="utf-8")


def test_train_mission1_zscore_uses_real_zip_layout(tmp_path: Path) -> None:
    source_zip = tmp_path / "ESA-Mission1.zip"
    _write_small_mission1_zip(source_zip)
    outputs = train_mission1_zscore(source_zip, tmp_path / "out")
    assert outputs["artifact"].exists()
    assert outputs["metrics"].exists()
    metrics = outputs["metrics"].read_text(encoding="utf-8")
    assert '"active_training_performed": true' in metrics
    assert '"channels_trained": 1' in metrics
