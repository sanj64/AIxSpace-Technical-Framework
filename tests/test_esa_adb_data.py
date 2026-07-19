from pathlib import Path

import pandas as pd
import pytest

from ad_dss.data.esa_adb import load_esa_metadata


def _write_metadata(root: Path) -> None:
    root.mkdir(parents=True)
    pd.DataFrame(
        {
            "Channel": ["channel_1", "channel_2"],
            "Subsystem": [0, 3],
            "Physical Unit": [0, 2],
            "Group": [1, 7],
            "Target": [0, 1],
        }
    ).to_csv(root / "channels_cleaned.csv", index=False)
    pd.DataFrame(
        {"ID": ["id_1"], "Channel": ["channel_2"], "StartTime": [10], "EndTime": [12]}
    ).to_csv(root / "labels_cleaned.csv", index=False)
    pd.DataFrame({"ID": ["id_1"], "Category": [2]}).to_csv(
        root / "anomaly_types_cleaned.csv", index=False
    )


def test_load_esa_metadata_preserves_channel_lookup(tmp_path: Path) -> None:
    _write_metadata(tmp_path / "ESA-M1" / "ESA-M1(preprocessed)")
    metadata = load_esa_metadata(tmp_path, "Mission1")

    assert metadata.mission == "ESA-M1"
    assert metadata.subsystem_for_channel("channel_2") == 3
    assert metadata.channels.loc[1, "Group"] == 7
    assert not metadata.has_telemetry


def test_load_esa_metadata_detects_local_telemetry_file(tmp_path: Path) -> None:
    root = tmp_path / "ESA-M1" / "ESA-M1(preprocessed)"
    _write_metadata(root)
    pd.DataFrame({"channel_1": [1.0]}).to_csv(root / "telemetry_channel_1.csv", index=False)

    metadata = load_esa_metadata(tmp_path, "M1")

    assert metadata.has_telemetry
    assert metadata.telemetry_files[0].name == "telemetry_channel_1.csv"


def test_load_esa_metadata_unknown_channel_raises(tmp_path: Path) -> None:
    _write_metadata(tmp_path / "ESA-M1" / "ESA-M1(preprocessed)")
    metadata = load_esa_metadata(tmp_path, "Mission1")

    with pytest.raises(KeyError):
        metadata.subsystem_for_channel("missing")
