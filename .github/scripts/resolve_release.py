from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

TAG_PATTERN = re.compile(r"[0-9]{8}(?:-r[0-9]+)?\Z")
SHA_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


def resolve_release_tag(
    requested: str,
    github_sha: str,
    checkout_sha: str,
    now: datetime | None = None,
) -> str:
    tag = requested.strip() or (now or datetime.now(UTC)).strftime("%Y%m%d")
    if not TAG_PATTERN.fullmatch(tag):
        raise ValueError(f"release tag must be YYYYMMDD or YYYYMMDD-rN: {tag!r}")
    try:
        datetime.strptime(tag[:8], "%Y%m%d")
    except ValueError:
        raise ValueError(f"release tag date is not a real date: {tag!r}") from None
    if not SHA_PATTERN.fullmatch(github_sha):
        raise ValueError("GITHUB_SHA must be a full commit hash")
    if checkout_sha.lower() != github_sha.lower():
        raise ValueError("checked out commit does not match GITHUB_SHA")
    return tag


def verify_existing_tag_target(tag: str, github_sha: str, existing_tag_sha: str | None) -> None:
    if existing_tag_sha is not None and existing_tag_sha.lower() != github_sha.lower():
        raise ValueError(f"tag {tag!r} already points at a different commit")


def _git(*arguments: str) -> str:
    result = subprocess.run(["git", *arguments], capture_output=True, check=True, text=True)
    return result.stdout.strip()


def _existing_tag_sha(tag: str) -> str | None:
    ref = f"refs/tags/{tag}"
    found = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", ref], capture_output=True, check=False
    )
    if found.returncode == 1:
        return None
    if found.returncode != 0:
        raise RuntimeError(f"could not inspect existing tag {tag!r}")
    return _git("rev-parse", "--verify", f"{ref}^{{commit}}")


def main() -> int:
    try:
        github_sha = os.environ["GITHUB_SHA"]
        tag = resolve_release_tag(
            os.environ.get("RELEASE_TAG_INPUT", ""),
            github_sha,
            _git("rev-parse", "HEAD"),
        )
        _git("check-ref-format", f"refs/tags/{tag}")
        verify_existing_tag_target(tag, github_sha, _existing_tag_sha(tag))
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as handle:
            handle.write(f"tag={tag}\n")
    except (KeyError, OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        print(f"release tag validation failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
