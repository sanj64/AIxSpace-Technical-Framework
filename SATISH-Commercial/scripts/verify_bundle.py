"""Verify SHA-256 checksums without extracting or trusting bundle content."""

from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path

from cryptography.exceptions import InvalidSignature

from satish_commercial.signing import load_public_key


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle_directory", type=Path)
    parser.add_argument("--public-key", type=Path, required=True)
    args = parser.parse_args()
    root = args.bundle_directory.resolve()
    checksum_file = root / "checksums.sha256"
    signature_file = root / "checksums.sha256.sig"
    try:
        signature = base64.b64decode(
            signature_file.read_text(encoding="ascii").strip(), validate=True
        )
        load_public_key(args.public_key).verify(signature, checksum_file.read_bytes())
    except (InvalidSignature, ValueError) as exc:
        raise SystemExit("bundle signature verification failed") from exc
    failures: list[str] = []
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", maxsplit=1)
        candidate = (root / relative).resolve()
        if root not in candidate.parents or not candidate.is_file():
            failures.append(f"unsafe or missing path: {relative}")
        elif digest(candidate) != expected:
            failures.append(f"checksum mismatch: {relative}")
    if failures:
        raise SystemExit("\n".join(failures))
    print("bundle checksums verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
