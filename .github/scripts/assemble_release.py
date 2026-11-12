from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tarfile
from pathlib import Path

TARGETS = ("aarch64-apple-darwin", "x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl")
PROFILES = ("play-sdk", "tools", "runtime")
TEST_ONLY_ASSETS = (("x86_64-unknown-linux-musl", "fixtures"),)
ARCHIVE_SUFFIX = ".tar.xz"
MANIFEST_SUFFIX = ".manifest.json"


def expected_stems(version: str) -> list[str]:
    pairs = [(target, profile) for target in TARGETS for profile in PROFILES] + list(TEST_ONLY_ASSETS)
    return sorted(f"ffmpeg-{profile}-{version}-{target}" for target, profile in pairs)


def expected_assets(version: str) -> list[str]:
    return sorted(
        f"{stem}{suffix}" for stem in expected_stems(version) for suffix in (ARCHIVE_SUFFIX, MANIFEST_SUFFIX)
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_commit(path: Path) -> str | None:
    member = f"{path.name.removesuffix(ARCHIVE_SUFFIX)}/share/ffmpeg-build/manifest.json"
    with tarfile.open(path, "r:xz") as archive:
        try:
            handle = archive.extractfile(member)
        except KeyError:
            raise ValueError(f"{path.name} has no {member}") from None
        if handle is None:
            raise ValueError(f"{path.name}: {member} is not a file")
        return json.load(handle).get("producer", {}).get("commit")


def check_manifest(path: Path, stem: str, version: str, commit: str, lock_sha256: str) -> None:
    manifest = json.loads(path.read_text())
    profile, _, target = stem.removeprefix("ffmpeg-").partition(f"-{version}-")
    expected = {
        "schema_version": 1,
        "product": f"ffmpeg-{profile}",
        "version": version,
        "target": target,
        "source_revision": commit,
        "sources_lock_sha256": lock_sha256,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"{path.name}: {key} is {manifest.get(key)!r}, expected {value!r}")


def assemble(found: list[Path], destination: Path, version: str, commit: str, lock_sha256: str) -> list[str]:
    wanted = expected_assets(version)
    by_name: dict[str, Path] = {}
    for path in found:
        if path.name in by_name:
            raise ValueError(f"duplicate asset {path.name}")
        by_name[path.name] = path
    if sorted(by_name) != wanted:
        missing = sorted(set(wanted) - set(by_name))
        extra = sorted(set(by_name) - set(wanted))
        raise ValueError(f"asset set mismatch: missing {missing}, unexpected {extra}")
    for stem in expected_stems(version):
        check_manifest(by_name[f"{stem}{MANIFEST_SUFFIX}"], stem, version, commit, lock_sha256)
        found_commit = archive_commit(by_name[f"{stem}{ARCHIVE_SUFFIX}"])
        if found_commit != commit:
            raise ValueError(f"{stem}{ARCHIVE_SUFFIX} was built from {found_commit!r}, not {commit}")
    destination.mkdir(parents=True, exist_ok=False)
    for name in wanted:
        shutil.copyfile(by_name[name], destination / name)
    (destination / "SHA256SUMS").write_text("".join(f"{sha256(destination / name)}  {name}\n" for name in wanted))
    return wanted


def main() -> int:
    if len(sys.argv) != 5:
        print("usage: assemble_release.py <artifacts-dir> <release-dir> <version> <commit>", file=sys.stderr)
        return 2
    source, destination, version, commit = sys.argv[1:]
    try:
        lock_sha256 = sha256(Path("sources.lock.json"))
        assets = assemble(
            sorted(p for p in Path(source).rglob("*") if p.name.endswith((ARCHIVE_SUFFIX, MANIFEST_SUFFIX))),
            Path(destination),
            version,
            commit,
            lock_sha256,
        )
    except (OSError, ValueError) as error:
        print(f"assemble failed: {error}", file=sys.stderr)
        return 1
    print("\n".join(assets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
