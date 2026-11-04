from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tarfile
from pathlib import Path

TARGETS = ("aarch64-apple-darwin", "x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl")
PROFILES = ("play-sdk", "tools")


def expected_assets(upstream: str, tag: str) -> list[str]:
    return sorted(
        f"ffmpeg-{upstream}+{tag}-{target}-{profile}.tar.gz" for target in TARGETS for profile in PROFILES
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_commit(path: Path) -> str | None:
    member = f"{path.name.removesuffix('.tar.gz')}/share/ffmpeg-build/manifest.json"
    with tarfile.open(path, "r:gz") as archive:
        try:
            handle = archive.extractfile(member)
        except KeyError:
            raise ValueError(f"{path.name} has no {member}") from None
        if handle is None:
            raise ValueError(f"{path.name}: {member} is not a file")
        return json.load(handle).get("producer", {}).get("commit")


def assemble(found: list[Path], destination: Path, upstream: str, tag: str, commit: str) -> dict:
    wanted = expected_assets(upstream, tag)
    by_name: dict[str, Path] = {}
    for path in found:
        if path.name in by_name:
            raise ValueError(f"duplicate asset {path.name}")
        by_name[path.name] = path
    if sorted(by_name) != wanted:
        missing = sorted(set(wanted) - set(by_name))
        extra = sorted(set(by_name) - set(wanted))
        raise ValueError(f"asset set mismatch: missing {missing}, unexpected {extra}")
    for name in wanted:
        found_commit = manifest_commit(by_name[name])
        if found_commit != commit:
            raise ValueError(f"{name} was built from {found_commit!r}, not {commit}")
    destination.mkdir(parents=True, exist_ok=False)
    assets = []
    for name in wanted:
        shutil.copyfile(by_name[name], destination / name)
        assets.append({"name": name, "sha256": sha256(destination / name), "size": (destination / name).stat().st_size})
    release = {"contract": 1, "tag": tag, "commit": commit, "upstream": upstream, "assets": assets}
    (destination / "release.json").write_text(json.dumps(release, indent=2, sort_keys=True) + "\n")
    lines = [f"{asset['sha256']}  {asset['name']}\n" for asset in assets]
    lines.append(f"{sha256(destination / 'release.json')}  release.json\n")
    (destination / "SHA256SUMS").write_text("".join(lines))
    return release


def main() -> int:
    if len(sys.argv) != 6:
        print("usage: assemble_release.py <artifacts-dir> <release-dir> <upstream> <tag> <commit>", file=sys.stderr)
        return 2
    source, destination, upstream, tag, commit = sys.argv[1:]
    try:
        release = assemble(sorted(Path(source).rglob("*.tar.gz")), Path(destination), upstream, tag, commit)
    except (OSError, ValueError) as error:
        print(f"assemble failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(release, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
