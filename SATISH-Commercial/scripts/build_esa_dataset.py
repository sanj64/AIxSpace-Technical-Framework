"""Build a SATISH replay CSV (+ config metadata) from the ESA-ADB Mission1 archive.

Example:
    python scripts/build_esa_dataset.py "C:/path/ESA-Mission1.zip" \
        --out datasets/esa-mission1/esa-mission1.csv

Produces the aligned wide telemetry CSV and a sibling ``*.meta.json`` describing the feature
order, subsystem map, and observed-range physical bounds for signed-config generation. This
is input-only telemetry: the archive's telecommands are never read and no command path is
created.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from satish_commercial.ingest.esa_adb import (
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    build_dataset,
    derive_physical_bounds,
    load_channels_metadata,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a SATISH replay CSV from ESA-ADB Mission1")
    parser.add_argument("archive", type=Path, help="path to ESA-Mission1.zip")
    parser.add_argument("--out", type=Path, required=True, help="output telemetry CSV path")
    parser.add_argument("--window-start", default=DEFAULT_WINDOW_START)
    parser.add_argument("--window-end", default=DEFAULT_WINDOW_END)
    parser.add_argument("--freq", default="5min", help="uniform resample cadence (pandas offset)")
    parser.add_argument("--max-gap-seconds", type=float, default=900.0)
    parser.add_argument(
        "--channels",
        default=None,
        help="comma-separated channel subset; default is all channels in channels.csv",
    )
    parser.add_argument("--bound-margin", type=float, default=0.05)
    args = parser.parse_args(argv)

    channels = tuple(args.channels.split(",")) if args.channels else None
    frame = build_dataset(
        args.archive,
        channels=channels,
        window_start=args.window_start,
        window_end=args.window_end,
        freq=args.freq,
        max_gap_seconds=args.max_gap_seconds,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.out, index=False)

    metadata = load_channels_metadata(args.archive)
    subsystem_lookup = {
        str(row.Channel): str(row.Subsystem)
        for row in metadata.itertuples()
        if str(row.Channel) in frame.columns
    }
    feature_columns = tuple(name for name in subsystem_lookup)
    bounds = derive_physical_bounds(frame, feature_columns, margin=args.bound_margin)
    meta_path = args.out.with_suffix(".meta.json")
    meta_path.write_text(
        json.dumps(
            {
                "dataset_id": "ESA-Mission1",
                "window": {"start": args.window_start, "end": args.window_end, "freq": args.freq},
                "rows": int(len(frame)),
                "feature_columns": list(feature_columns),
                "subsystem_lookup": subsystem_lookup,
                "physical_bounds": bounds,
                "label_column": "anomaly_label",
                "anomaly_rows": int(frame["anomaly_label"].sum()),
                "bounds_note": "observed-range envelope, not a vendor or flight specification",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "csv": str(args.out),
                "meta": str(meta_path),
                "rows": int(len(frame)),
                "features": len(feature_columns),
                "anomaly_rows": int(frame["anomaly_label"].sum()),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
