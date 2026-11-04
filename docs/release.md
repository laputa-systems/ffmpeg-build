# Release

Releases are produced only by `.github/workflows/release.yml`. The workflow runs the same commands as a local build.

## Publish

```sh
git push origin main
gh workflow run release.yml -f release_tag=YYYYMMDD
gh run watch
gh release view YYYYMMDD --json tagName,isPrerelease,assets
```

With an empty `release_tag`, the tag defaults to the current UTC date. Use `YYYYMMDD` for the first release of a UTC day and `YYYYMMDD-rN` for later revisions. `.github/scripts/resolve_release.py` rejects any other format. It also rejects a checkout that is not `GITHUB_SHA`, and an existing tag that points at a different commit.

A release is never overwritten. If `publish` finds an existing release for the tag, it fails; rerun with the next `-rN`. No job moves a tag or replaces an asset.

Releases are normal, not prereleases. Consumers enumerate `https://github.com/laputa-systems/ffmpeg-build/releases.atom` rather than `/releases/latest`.

## Jobs

| Job | Runner | Does |
| --- | --- | --- |
| `prepare` | `ubuntu-latest` | resolves the tag, reads the upstream version, runs `python3 -m unittest discover -s tests` |
| `fixtures` | `ubuntu-latest` | `scripts/linux-fixtures.sh`: test fixtures from Alpine FFmpeg 9.0.2 |
| `build-macos` | `xcode-27` (Xcode 27.1) | `build`, `audit`, `package` for both profiles; `tests/tools-workflows.sh` |
| `build-linux` | `ubuntu-latest`, `ubuntu-24.04-arm` | `scripts/linux-build.sh` for both profiles (native, in the digest-pinned Alpine image); `package` |
| `assemble` | `ubuntu-latest` | `.github/scripts/assemble_release.py`: exactly six archives, `release.json`, `SHA256SUMS` |
| `qualify-macos` | `xcode-27` | verifies `SHA256SUMS`, then `build.py qualify` on the assembled bytes |
| `qualify-linux` | `ubuntu-latest`, `ubuntu-24.04-arm` | verifies `SHA256SUMS`, then `scripts/linux-qualify.sh` on the assembled bytes |
| `publish` | `ubuntu-latest` | the only job with `contents: write`; refuses an existing release, creates the tag at `GITHUB_SHA`, downloads the published assets and verifies them |

Every action is pinned to a full commit SHA. The Alpine images are pinned by digest in `docker/Dockerfile`, the same digests `python-build` uses. The only cache holds verified source tarballs. Its key covers the source lock, the profiles, `build.py`, the scripts, the Dockerfile, the target, and the Xcode version on macOS.

## Assets

- Six archives: `ffmpeg-<upstream>+<tag>-<target>-<profile>.tar.gz` for the three targets and two profiles. See `docs/artifacts.md`.
- `release.json`: `contract`, `tag`, `commit`, `upstream`, and each asset's `name`, `sha256`, and `size`.
- `SHA256SUMS`: one line per archive, plus `release.json`.

## Update FFmpeg

1. Change `sources.lock.json`: version, URL, filename, archive root, and the real SHA-256.
2. Run the local matrix: `build` and `audit` for both macOS profiles, `scripts/linux-build.sh` for both Linux targets and profiles, `tests/tools-workflows.sh`, `tests/encode-command.sh`, then `package` and `qualify`.
3. Publish a new `YYYYMMDD` or `YYYYMMDD-rN` release.
4. Update `play/ffmpeg-sdk.lock.json` with the new tag and the published SHA-256 values. Rebuild and qualify Player, and publish a Player patch release.
5. `usr` discovers the new tools release from `releases.atom`.

Never point a consumer at a tag before its release and checksums exist.
