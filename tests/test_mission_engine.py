"""Tests for core/mission_engine.py."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ad_dss.common.schemas import MissionEvent
from ad_dss.core.mission_engine import MissionEngine

CONFIG = "config/settings.yaml"
FIXTURE = Path("tests/fixtures/telemetry_fixture.csv")


@pytest.fixture()
def engine() -> MissionEngine:
    return MissionEngine(CONFIG)


# ── run_batch ─────────────────────────────────────────────────────────────────

def test_run_batch_zscore_returns_dict(engine: MissionEngine) -> None:
    results = engine.run_batch(FIXTURE, method="zscore", train=False)
    assert isinstance(results, dict)
    required = ["anomalies", "risks", "decisions", "backups", "telemetry_df", "scores", "method"]
    for key in required:
        assert key in results, f"Missing key: {key}"


def test_run_batch_anomalies_not_empty(engine: MissionEngine) -> None:
    results = engine.run_batch(FIXTURE, method="zscore", train=False)
    assert len(results["anomalies"]) > 0


def test_run_batch_telemetry_is_dataframe(engine: MissionEngine) -> None:
    results = engine.run_batch(FIXTURE, method="zscore", train=False)
    assert isinstance(results["telemetry_df"], pd.DataFrame)
    assert not results["telemetry_df"].empty


def test_run_batch_if_method(engine: MissionEngine) -> None:
    results = engine.run_batch(FIXTURE, method="isolation_forest", train=True)
    assert results["method"] == "isolation_forest"
    assert len(results["anomalies"]) > 0


def test_run_batch_has_kpi_table(engine: MissionEngine) -> None:
    results = engine.run_batch(FIXTURE, method="zscore", train=False)
    kpi = results["kpi_table"]
    assert "Anomalies flagged" in kpi
    assert "Runtime (s)" in kpi


def test_run_batch_missing_file_raises(engine: MissionEngine) -> None:
    with pytest.raises(FileNotFoundError):
        engine.run_batch("nonexistent.csv", method="zscore")


def test_run_batch_phases_built(engine: MissionEngine) -> None:
    results = engine.run_batch(FIXTURE, method="zscore", train=False)
    assert "phases" in results
    assert len(results["phases"]) > 0


# ── run_replay ────────────────────────────────────────────────────────────────

def test_run_replay_yields_events(engine: MissionEngine) -> None:
    gen = engine.run_replay(FIXTURE, method="zscore", train=False)
    events = [next(gen) for _ in range(3)]
    assert len(events) == 3
    assert all(isinstance(e, MissionEvent) for e in events)


def test_run_replay_event_structure(engine: MissionEngine) -> None:
    gen = engine.run_replay(FIXTURE, method="zscore", train=False)
    event = next(gen)
    assert isinstance(event.step, int)
    assert isinstance(event.timestamp, pd.Timestamp)
    assert isinstance(event.phase.name, str)
    assert isinstance(event.telemetry_snapshot, dict)
    assert len(event.telemetry_snapshot) > 0


def test_run_replay_step_increments(engine: MissionEngine) -> None:
    gen = engine.run_replay(FIXTURE, method="zscore", train=False, window_step=5)
    steps = [next(gen).step for _ in range(4)]
    assert steps == [0, 5, 10, 15]


def test_run_replay_all_steps(engine: MissionEngine) -> None:
    gen = engine.run_replay(FIXTURE, method="zscore", train=False)
    events = list(gen)
    assert len(events) == 200  # fixture has 200 rows


# ── Report integration ────────────────────────────────────────────────────────

def test_generate_report_from_batch(engine: MissionEngine, tmp_path: Path) -> None:
    results = engine.run_batch(FIXTURE, method="zscore", train=False)
    csv_p, pdf_p = engine.generate_and_save_report(results, tmp_path)
    assert csv_p.exists()
    assert pdf_p.exists()
