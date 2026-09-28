"""Publish a short run summary as a GitHub Actions notice annotation (public, via API)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

CHUNK = 3000
METADATA_KEYS = (
    "snapshot_id",
    "service_dates",
    "service_date_notes",
    "feed",
    "counts",
    "osm_poi_stats",
    "routing",
)


def escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def main(filenames: list[str]) -> None:
    parts = []
    for filename in filenames:
        path = Path(filename)
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if path.name == "run_metadata.json":
            data = {key: data.get(key) for key in METADATA_KEYS}
        parts.append(f"{path.name}: {json.dumps(data, ensure_ascii=False)}")
    text = "\n".join(parts) or "no metadata written"
    for index, start in enumerate(range(0, len(text), CHUNK), start=1):
        print(f"::notice title=Run summary ({index})::{escape(text[start:start + CHUNK])}")


if __name__ == "__main__":
    main(sys.argv[1:])
