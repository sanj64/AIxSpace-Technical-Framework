"""Mission 1 ESA-ADB event-wise evaluation CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ad_dss.data.esa_adb import load_esa_metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ESA-ADB Mission 1 event-wise evaluation.")
    parser.add_argument("--subsystem", required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    metadata = load_esa_metadata(args.data_dir, "Mission1")
    if not metadata.has_telemetry:
        print(
            "ERROR: ESA Mission 1 telemetry not downloaded; metadata-only files are present. "
            "Run scripts/download_esa_adb.py before producing metrics.",
            file=sys.stderr,
        )
        return 2
    print(
        "ERROR: ESA Mission 1 telemetry evaluation is not implemented for downloaded telemetry yet.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
