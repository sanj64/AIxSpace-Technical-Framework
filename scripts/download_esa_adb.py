"""Download ESA Anomaly Dataset mission archives from Zenodo."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any
from urllib.request import urlopen

RECORD_ID = "12528696"
ZENODO_RECORD_URL = f"https://zenodo.org/api/records/{RECORD_ID}"

MISSION_ALIASES = {
    "mission1": ("esa-m1", "m1", "mission1", "mission 1"),
    "mission2": ("esa-m2", "m2", "mission2", "mission 2"),
    "mission3": ("esa-m3", "m3", "mission3", "mission 3"),
}


def fetch_zenodo_record(url: str = ZENODO_RECORD_URL) -> dict[str, Any]:
    """Fetch Zenodo record metadata."""
    with urlopen(url, timeout=30) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def mission_key(raw: str) -> str:
    normalized = raw.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if normalized in {"1", "m1", "mission1", "esam1"}:
        return "mission1"
    if normalized in {"2", "m2", "mission2", "esam2"}:
        return "mission2"
    if normalized in {"3", "m3", "mission3", "esam3"}:
        return "mission3"
    raise ValueError("mission must be one of Mission1, Mission2, or Mission3")


def select_mission_file(record: dict[str, Any], mission: str) -> dict[str, Any]:
    """Select the first Zenodo file whose key matches the requested mission."""
    key = mission_key(mission)
    aliases = MISSION_ALIASES[key]
    for file_info in record.get("files", []):
        name = str(file_info.get("key", "")).lower()
        name_compact = name.replace("-", "").replace("_", "").replace(" ", "")
        if any(alias.replace("-", "").replace(" ", "") in name_compact for alias in aliases):
            return file_info
    raise FileNotFoundError(f"No Zenodo file found for {mission}")


def checksum_parts(checksum: str | None) -> tuple[str, str] | None:
    if not checksum:
        return None
    if ":" in checksum:
        algorithm, digest = checksum.split(":", 1)
    else:
        algorithm, digest = "md5", checksum
    algorithm = algorithm.lower()
    if algorithm not in hashlib.algorithms_available:
        return None
    return algorithm, digest.lower()


def verify_checksum(path: Path, checksum: str | None) -> bool:
    parts = checksum_parts(checksum)
    if parts is None:
        return True
    algorithm, expected = parts
    hasher = hashlib.new(algorithm)
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest().lower() == expected


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=60) as response, destination.open("wb") as fh:
        shutil.copyfileobj(response, fh)


def file_download_url(file_info: dict[str, Any]) -> str:
    links = file_info.get("links", {})
    url = links.get("self") or links.get("download")
    if not url:
        raise ValueError("Zenodo file metadata does not include a download URL")
    return str(url)


def download_mission(mission: str, data_dir: Path, record: dict[str, Any] | None = None) -> Path:
    record = record or fetch_zenodo_record()
    file_info = select_mission_file(record, mission)
    name = str(file_info["key"])
    destination = data_dir / name
    download_file(file_download_url(file_info), destination)
    checksum = file_info.get("checksum")
    if not verify_checksum(destination, str(checksum) if checksum else None):
        destination.unlink(missing_ok=True)
        raise ValueError(f"Checksum verification failed for {destination}")
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download ESA-ADB mission archives from Zenodo.")
    parser.add_argument("--mission", required=True, help="Mission1, Mission2, or Mission3")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Print the selected Zenodo file metadata without downloading it.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        record = fetch_zenodo_record()
        file_info = select_mission_file(record, args.mission)
        if args.manifest_only:
            print(json.dumps(file_info, indent=2, sort_keys=True))
            return 0
        destination = download_mission(args.mission, args.data_dir, record=record)
        print(f"Downloaded {destination}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
