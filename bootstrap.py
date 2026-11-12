"""Make the laputa-buildlib wheel pinned in sources.lock.json importable without a virtual environment."""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".work" / "cache" / "sources"
PIN = "laputa-buildlib"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wheel() -> Path:
    inputs = json.loads((ROOT / "sources.lock.json").read_text())["inputs"]
    pin = next(item for item in inputs if item["name"] == PIN)
    path = CACHE / pin["filename"]
    if path.is_file() and _digest(path) == pin["sha256"]:
        return path
    CACHE.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    try:
        with urllib.request.urlopen(pin["url"], timeout=120) as response:
            part.write_bytes(response.read())
        if _digest(part) != pin["sha256"]:
            raise SystemExit(f"error: {pin['url']} does not match the sha256 pinned for {PIN}")
        part.replace(path)
    finally:
        part.unlink(missing_ok=True)
    return path


sys.path.insert(0, str(_wheel()))

from buildlib import hashing, locks, release, targets

__all__ = ["CACHE", "hashing", "locks", "release", "targets"]
