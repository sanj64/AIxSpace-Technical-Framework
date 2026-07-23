"""Download a counsel-approved dataset URL and require an expected SHA-256 hash."""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="approved direct file URL from the dataset record")
    parser.add_argument("--sha256", required=True, help="expected published/approved SHA-256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("refusing to overwrite an existing dataset file")
    if urlparse(args.url).scheme.lower() != "https":
        raise ValueError("dataset downloads require an approved HTTPS URL")
    digest = hashlib.sha256()
    request = urllib.request.Request(  # noqa: S310 - HTTPS is enforced above
        args.url, headers={"User-Agent": "SATISH-dataset-downloader/1.0"}
    )
    with (
        urllib.request.urlopen(  # noqa: S310  # nosec B310
            request, timeout=30
        ) as response,
        args.output.open("xb") as output,
    ):
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest().lower() != args.sha256.lower():
        args.output.unlink(missing_ok=True)
        raise ValueError("downloaded dataset hash does not match; file was removed")
    print(f"verified dataset written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
