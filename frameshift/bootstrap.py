"""Load static resources for explicitly supplied validation inputs."""

import json
from pathlib import Path


def published_identities(releases: Path) -> list[dict]:
    """Read reviewed release records, not installed prompt self-declarations."""
    entries: list[dict] = []
    for path in sorted(releases.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        entries.extend(record["prompts"])
    return entries
