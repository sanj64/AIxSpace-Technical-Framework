from pathlib import Path

import pytest
from scripts.download_esa_adb import (
    checksum_parts,
    download_mission,
    select_mission_file,
    verify_checksum,
)


def _record() -> dict:
    return {
        "files": [
            {
                "key": "ESA-M1(preprocessed).zip",
                "links": {"self": "https://example.invalid/esa-m1.zip"},
                "checksum": "md5:900150983cd24fb0d6963f7d28e17f72",
            },
            {
                "key": "ESA-M2(preprocessed).zip",
                "links": {"self": "https://example.invalid/esa-m2.zip"},
            },
        ]
    }


def test_select_mission_file_uses_mission_alias() -> None:
    selected = select_mission_file(_record(), "Mission1")

    assert selected["key"] == "ESA-M1(preprocessed).zip"


def test_checksum_parts_defaults_to_md5() -> None:
    assert checksum_parts("900150983cd24fb0d6963f7d28e17f72") == (
        "md5",
        "900150983cd24fb0d6963f7d28e17f72",
    )


def test_verify_checksum_accepts_matching_digest(tmp_path: Path) -> None:
    path = tmp_path / "payload.txt"
    path.write_text("abc")

    assert verify_checksum(path, "md5:900150983cd24fb0d6963f7d28e17f72")


def test_download_mission_uses_mocked_download_boundary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_download(url: str, destination: Path) -> None:
        assert url == "https://example.invalid/esa-m1.zip"
        destination.write_text("abc")

    monkeypatch.setattr("scripts.download_esa_adb.download_file", fake_download)

    destination = download_mission("M1", tmp_path, record=_record())

    assert destination.name == "ESA-M1(preprocessed).zip"
    assert destination.read_text() == "abc"
