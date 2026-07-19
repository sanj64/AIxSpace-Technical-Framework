"""ESA Anomaly Dataset metadata loading helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REQUIRED_METADATA = (
    "channels_cleaned.csv",
    "labels_cleaned.csv",
    "anomaly_types_cleaned.csv",
)
OPTIONAL_METADATA = ("events_cleaned.csv", "telecommands_cleaned.csv")
METADATA_FILES = set(REQUIRED_METADATA + OPTIONAL_METADATA)


@dataclass(frozen=True)
class EsaMetadata:
    mission: str
    root: Path
    channels: pd.DataFrame
    labels: pd.DataFrame
    anomaly_types: pd.DataFrame
    events: pd.DataFrame | None
    telecommands: pd.DataFrame | None
    telemetry_files: tuple[Path, ...]

    @property
    def has_telemetry(self) -> bool:
        return bool(self.telemetry_files)

    def subsystem_for_channel(self, channel: str) -> int:
        matches = self.channels.loc[self.channels["Channel"] == channel, "Subsystem"]
        if matches.empty:
            raise KeyError(f"Unknown ESA channel: {channel}")
        return int(matches.iloc[0])


def mission_key(raw: str) -> str:
    normalized = raw.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if normalized in {"1", "m1", "mission1", "esam1"}:
        return "ESA-M1"
    if normalized in {"2", "m2", "mission2", "esam2"}:
        return "ESA-M2"
    if normalized in {"3", "m3", "mission3", "esam3"}:
        return "ESA-M3"
    raise ValueError("mission must be one of Mission1, Mission2, or Mission3")


def find_mission_metadata_dir(data_dir: Path, mission: str) -> Path:
    mission_dir = data_dir / mission_key(mission)
    candidates = [mission_dir, *mission_dir.glob("*preprocessed*")]
    for candidate in candidates:
        if candidate.is_dir() and all((candidate / name).exists() for name in REQUIRED_METADATA):
            return candidate
    raise FileNotFoundError(f"ESA metadata files not found for {mission} under {data_dir}")


def _read_optional_csv(root: Path, name: str) -> pd.DataFrame | None:
    path = root / name
    return pd.read_csv(path) if path.exists() else None


def find_telemetry_files(root: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    for path in root.rglob("*.csv"):
        if path.name not in METADATA_FILES:
            files.append(path)
    return tuple(sorted(files))


def load_esa_metadata(data_dir: Path, mission: str) -> EsaMetadata:
    root = find_mission_metadata_dir(data_dir, mission)
    channels = pd.read_csv(root / "channels_cleaned.csv")
    labels = pd.read_csv(root / "labels_cleaned.csv")
    anomaly_types = pd.read_csv(root / "anomaly_types_cleaned.csv")
    return EsaMetadata(
        mission=mission_key(mission),
        root=root,
        channels=channels,
        labels=labels,
        anomaly_types=anomaly_types,
        events=_read_optional_csv(root, "events_cleaned.csv"),
        telecommands=_read_optional_csv(root, "telecommands_cleaned.csv"),
        telemetry_files=find_telemetry_files(root),
    )
