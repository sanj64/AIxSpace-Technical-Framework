"""Telemetry ingestion: load CSV/JSON or generate synthetic multi-subsystem data."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from ad_dss.common.logging_config import get_logger
from ad_dss.common.schemas import TelemetryFrame

logger = get_logger(__name__)

_DEFAULT_SUBSYSTEMS = ["EPS", "ADCS", "COM", "Thermal"]


class TelemetryHandler:
    def __init__(self, config_path: str | Path = "config/settings.yaml") -> None:
        config_path = Path(config_path)
        with open(config_path) as f:
            cfg: dict[str, Any] = yaml.safe_load(f)
        tel = cfg.get("telemetry", {})
        self.timestamp_col: str = tel.get("timestamp_col", "timestamp")
        self.subsystems: list[str] = tel.get("subsystems", _DEFAULT_SUBSYSTEMS)
        self.start_date: datetime = datetime.fromisoformat(
            tel.get("start_date", "2025-01-01 00:00:00")
        )

    # ── Public API ──────────────────────────────────────────────────────────

    def load(self, source_path: str | Path) -> pd.DataFrame:
        """Load telemetry from CSV or JSON; parse timestamps; return sorted DataFrame."""
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"Telemetry file not found: {path}")

        if path.suffix.lower() == ".json":
            df = pd.read_json(path)
        else:
            df = pd.read_csv(path, low_memory=False)

        df = self._parse_timestamps(df)
        logger.info("Loaded telemetry from %s: shape=%s", path, df.shape)
        return df.sort_index()

    def generate_synthetic(
        self,
        n_points: int = 500,
        subsystems: list[str] | None = None,
        seed: int = 42,
    ) -> pd.DataFrame:
        """Generate multi-subsystem synthetic telemetry with injected anomalies."""
        rng = np.random.default_rng(seed)
        subs = subsystems or self.subsystems
        t = [self.start_date + timedelta(seconds=i) for i in range(n_points)]

        cols: dict[str, np.ndarray] = {"timestamp": np.array(t, dtype="object")}
        for sub in subs:
            cols.update(_generate_subsystem_channels(sub, n_points, rng))

        df = pd.DataFrame(cols)
        df = self._parse_timestamps(df)
        logger.info("Generated synthetic telemetry: shape=%s, subsystems=%s", df.shape, subs)
        return df

    def to_telemetry_frame(self, df: pd.DataFrame) -> TelemetryFrame:
        """Wrap a DataFrame in a TelemetryFrame with auto-detected subsystems."""
        detected = _detect_subsystems(df.columns.tolist())
        return TelemetryFrame(df=df, subsystems=detected or self.subsystems, source="handler")

    # ── Internals ───────────────────────────────────────────────────────────

    def _parse_timestamps(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        ts_col = None
        for candidate in [self.timestamp_col, "timestamp", "time", "Timestamp", "Time"]:
            if candidate in df.columns:
                ts_col = candidate
                break
        if ts_col is not None:
            df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
            df = df.set_index(ts_col)
        return df


def _generate_subsystem_channels(
    subsystem: str, n: int, rng: np.random.Generator
) -> dict[str, np.ndarray]:
    """Return synthetic numeric channels for a named subsystem."""
    if subsystem == "EPS":
        voltage = 3.7 + 0.02 * np.sin(np.arange(n) / 12) + 0.01 * rng.standard_normal(n)
        current = 0.15 + 0.01 * rng.standard_normal(n)
        temp = 24.0 + 0.2 * rng.standard_normal(n)
        voltage[int(n * 0.15)] = 5.0  # injected spike
        current[int(n * 0.70)] = 0.5
        return {
            "EPS_voltage": voltage,
            "EPS_current": current,
            "EPS_temp": temp,
        }
    if subsystem == "ADCS":
        roll = 0.02 * rng.standard_normal(n)
        pitch = 0.02 * rng.standard_normal(n)
        yaw = 0.02 * rng.standard_normal(n)
        roll[int(n * 0.45)] = 0.5  # attitude anomaly
        return {"ADCS_roll": roll, "ADCS_pitch": pitch, "ADCS_yaw": yaw}
    if subsystem == "COM":
        rssi = -80.0 + 5 * rng.standard_normal(n)
        bitrate = 9600.0 + 100 * rng.standard_normal(n)
        bitrate[int(n * 0.60)] = 0.0  # link loss
        return {"COM_rssi": rssi, "COM_bitrate": bitrate}
    if subsystem == "Thermal":
        t_board = 35.0 + 0.3 * rng.standard_normal(n)
        t_bat = 28.0 + 0.2 * rng.standard_normal(n)
        ramp = np.zeros(n)
        ramp_start = int(n * 0.55)
        ramp[ramp_start:] = np.linspace(0, 30, n - ramp_start)
        t_board = t_board + ramp
        return {"Thermal_board": t_board, "Thermal_battery": t_bat}
    # Generic fallback
    ch = rng.standard_normal(n)
    ch[int(n * 0.5)] += 5.0
    return {f"{subsystem}_channel0": ch}


def _detect_subsystems(columns: list[str]) -> list[str]:
    seen: list[str] = []
    for col in columns:
        if "_" in col:
            prefix = col.split("_")[0]
            if prefix not in seen:
                seen.append(prefix)
    return seen


def load_telemetry(
    source_path: str | Path, config_path: str | Path = "config/settings.yaml"
) -> pd.DataFrame:
    """Convenience function: load CSV/JSON telemetry without creating a handler."""
    return TelemetryHandler(config_path).load(source_path)
