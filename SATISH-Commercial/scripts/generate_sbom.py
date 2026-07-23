"""Generate an SPDX 2.3 inventory from the reviewed transitive runtime lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

PACKAGE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)")


def locked_packages(path: Path) -> list[tuple[str, str]]:
    packages: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = PACKAGE.match(line)
        if match:
            packages.append((match.group(1), match.group(2)))
    if not packages:
        raise ValueError("the requirements lock contains no pinned packages")
    return packages


def created_time() -> str:
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    moment = datetime.fromtimestamp(int(epoch), UTC) if epoch else datetime.now(UTC)
    return moment.isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, default=Path("requirements.lock"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    locked = locked_packages(args.requirements)
    packages = []
    for name, version in locked:
        identity = hashlib.sha256(f"{name}=={version}".encode()).hexdigest()[:16]
        packages.append(
            {
                "SPDXID": f"SPDXRef-Package-{identity}",
                "name": name,
                "versionInfo": version,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "copyrightText": "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": f"pkg:pypi/{name.lower()}@{version}",
                    }
                ],
            }
        )
    namespace_hash = hashlib.sha256(json.dumps(packages, sort_keys=True).encode()).hexdigest()
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "SATISH-Commercial-runtime-SBOM",
        "documentNamespace": f"https://sbom.satish.invalid/{namespace_hash}",
        "creationInfo": {
            "created": created_time(),
            "creators": ["Tool: SATISH-lock-to-spdx-1.0.0"],
        },
        "packages": packages,
        "annotations": [
            {
                "annotationType": "OTHER",
                "annotator": "Tool: SATISH-lock-to-spdx-1.0.0",
                "annotationDate": created_time(),
                "comment": (
                    "License fields remain NOASSERTION until authoritative license texts "
                    "and counsel review are attached to the release."
                ),
            }
        ],
    }
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
