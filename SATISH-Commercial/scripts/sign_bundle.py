"""Sign an immutable bundle checksum manifest with an offline Ed25519 release key."""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

from satish_commercial.signing import load_private_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle_directory", type=Path)
    parser.add_argument("--private-key", type=Path, required=True)
    args = parser.parse_args()
    checksums = args.bundle_directory / "checksums.sha256"
    signature = args.bundle_directory / "checksums.sha256.sig"
    if signature.exists():
        raise FileExistsError("refusing to overwrite an existing bundle signature")
    signed = load_private_key(args.private_key).sign(checksums.read_bytes())
    signature.write_text(base64.b64encode(signed).decode("ascii") + "\n", encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
