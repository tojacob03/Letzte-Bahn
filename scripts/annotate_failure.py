"""Print the tail of log files as GitHub Actions error annotations.

Workflow logs of public repositories are visible to signed-in users only, whereas
annotations are public and available through the REST API. This keeps failures of the
CI and the data pipeline debuggable from anywhere.
"""

from __future__ import annotations

import sys
from pathlib import Path

MAX_LINES = 80
CHUNK = 3000


def escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main(filenames: list[str]) -> None:
    for filename in filenames:
        path = Path(filename)
        if not path.exists():
            continue
        text = "\n".join(path.read_text(errors="replace").splitlines()[-MAX_LINES:])
        for index, start in enumerate(range(0, len(text), CHUNK), start=1):
            print(f"::error title={path.name} ({index})::{escape(text[start:start + CHUNK])}")


if __name__ == "__main__":
    main(sys.argv[1:])
