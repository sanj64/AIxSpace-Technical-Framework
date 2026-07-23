"""Create a deterministic checksum manifest for an already approved bundle directory."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle_directory", type=Path)
    args = parser.parse_args()
    root = args.bundle_directory.resolve()
    checksum_path = root / "checksums.sha256"
    if checksum_path.exists():
        raise FileExistsError("refusing to overwrite an existing checksum manifest")
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.name not in {"checksums.sha256", "checksums.sha256.sig"}
    ]
    if not files:
        raise ValueError("bundle directory contains no files")
    lines: list[str] = []
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise ValueError(f"symbolic links are prohibited in a release bundle: {path}")
        lines.append(f"{digest(path)}  {path.relative_to(root).as_posix()}")
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
