"""Tests for telemetry/handler.py."""

from pathlib import Path

import pandas as pd
import pytest

from ad_dss.common.schemas import TelemetryFrame
from ad_dss.telemetry.handler import TelemetryHandler, _detect_subsystems

CONFIG = "config/settings.yaml"
FIXTURE = Path("tests/fixtures/telemetry_fixture.csv")


@pytest.fixture()
def handler() -> TelemetryHandler:
    return TelemetryHandler(CONFIG)


def test_load_csv(handler: TelemetryHandler) -> None:
    df = handler.load(FIXTURE)
    assert isinstance(df, pd.DataFrame)
    assert df.shape[0] == 200
    assert isinstance(df.index, pd.DatetimeIndex)


def test_load_missing_raises(handler: TelemetryHandler) -> None:
    with pytest.raises(FileNotFoundError):
        handler.load("nonexistent.csv")


def test_generate_synthetic_default(handler: TelemetryHandler) -> None:
    df = handler.generate_synthetic(n_points=100)
    assert isinstance(df, pd.DataFrame)
    assert df.shape[0] == 100
    assert isinstance(df.index, pd.DatetimeIndex)
    # Should have columns from all 4 default subsystems
    assert any("EPS" in c for c in df.columns)
    assert any("Thermal" in c for c in df.columns)


def test_generate_synthetic_reproducible(handler: TelemetryHandler) -> None:
    df1 = handler.generate_synthetic(n_points=50, seed=0)
    df2 = handler.generate_synthetic(n_points=50, seed=0)
    assert (df1.values == df2.values).all()


def test_to_telemetry_frame(handler: TelemetryHandler) -> None:
    df = handler.generate_synthetic(n_points=50)
    frame = handler.to_telemetry_frame(df)
    assert isinstance(frame, TelemetryFrame)
    assert len(frame.subsystems) >= 1
    assert frame.df is df


def test_detect_subsystems() -> None:
    cols = ["EPS_voltage", "EPS_current", "ADCS_roll", "COM_rssi"]
    subs = _detect_subsystems(cols)
    assert "EPS" in subs
    assert "ADCS" in subs
    assert "COM" in subs
