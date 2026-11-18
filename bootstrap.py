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
    lock: object = json.loads((ROOT / "sources.lock.json").read_text())
    if not isinstance(lock, dict):
        raise TypeError("invalid sources lock")
    inputs: object = lock.get("inputs")
    if not isinstance(inputs, list):
        raise TypeError("invalid sources lock inputs")
    for item in inputs:
        if not isinstance(item, dict):
            raise TypeError("invalid sources lock input")
        if item.get("name") == PIN:
            pin = item
            break
    else:
        raise ValueError(f"missing {PIN} source")
    filename: object = pin.get("filename")
    url: object = pin.get("url")
    sha256: object = pin.get("sha256")
    if not isinstance(filename, str):
        raise TypeError(f"invalid {PIN} filename")
    if not isinstance(url, str):
        raise TypeError(f"invalid {PIN} url")
    if not isinstance(sha256, str):
        raise TypeError(f"invalid {PIN} sha256")
    path = CACHE / filename
    if path.is_file() and _digest(path) == sha256:
        return path
    CACHE.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            part.write_bytes(response.read())
        if _digest(part) != sha256:
            raise SystemExit(f"error: {url} does not match the sha256 pinned for {PIN}")
        part.replace(path)
    finally:
        part.unlink(missing_ok=True)
    return path


sys.path.insert(0, str(_wheel()))

from buildlib import hashing, locks, release, targets

__all__ = ["CACHE", "hashing", "locks", "release", "targets"]
