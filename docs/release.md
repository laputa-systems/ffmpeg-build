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
| `build-macos` | `xcode-27` (Xcode 27.1) | `build`, `audit`, `package` for all three profiles; `tests/tools-workflows.sh` on the tools and runtime stages |
| `build-linux` | `ubuntu-latest`, `ubuntu-24.04-arm` | `scripts/linux-build.sh` for all three profiles (native, in the digest-pinned Alpine image); `package` |
| `assemble` | `ubuntu-latest` | `.github/scripts/assemble_release.py`: exactly nine archives, `release.json`, `SHA256SUMS` |
| `qualify-macos` | `xcode-27` | verifies `SHA256SUMS`, then `build.py qualify` on the assembled bytes |
| `qualify-linux` | `ubuntu-latest`, `ubuntu-24.04-arm` | verifies `SHA256SUMS`, then `scripts/linux-qualify.sh` on the assembled bytes |
| `publish` | `ubuntu-latest` | the only job with `contents: write`; refuses an existing release, creates the tag at `GITHUB_SHA`, downloads the published assets and verifies them |

Every action is pinned to a full commit SHA. The Alpine images are pinned by digest in `docker/Dockerfile`, the same digests `python-build` uses. The only cache holds verified source tarballs. Its key covers the source lock, the profiles, `build.py`, the scripts, the Dockerfile, the target, and the Xcode version on macOS.

## Assets

- Nine archives: `ffmpeg-<upstream>+<tag>-<target>-<profile>.tar.gz` for the three targets and the `runtime`, `play-sdk`, and `tools` profiles. See `docs/artifacts.md`.
- `release.json`: `contract`, `tag`, `commit`, `upstream`, and each asset's `name`, `sha256`, and `size`.
- `SHA256SUMS`: one line per archive, plus `release.json`.

## Update FFmpeg

1. Change `sources.lock.json`: version, URL, filename, archive root, and the real SHA-256.
2. Run the local matrix: `build` and `audit` for the three macOS profiles, `scripts/linux-build.sh` for both Linux targets and the three profiles, `tests/tools-workflows.sh`, `tests/encode-command.sh`, then `package` and `qualify`.
3. Publish a new `YYYYMMDD` or `YYYYMMDD-rN` release.
4. Update `play/ffmpeg-sdk.lock.json` with the new tag and the published SHA-256 values. Rebuild and qualify Player, and publish a Player patch release.
5. `usr` discovers the new tools release from `releases.atom`.

Never point a consumer at a tag before its release and checksums exist.

## Current release: `20261104`

Built from `d611d42`; FFmpeg 9.0.2, dav1d 1.5.4, zlib 1.3.2.

| Target | `play-sdk` | `tools` | Consumer links (SDK) | Tools runtime dependencies |
| --- | ---: | ---: | --- | --- |
| `aarch64-apple-darwin` | 13,792,303 B | 7,528,937 B | VideoToolbox, CoreFoundation, CoreMedia, CoreVideo, CoreServices | `libSystem` and the AudioToolbox, VideoToolbox, CoreFoundation, CoreMedia, CoreVideo, CoreServices frameworks |
| `x86_64-unknown-linux-musl` | 20,864,634 B | 11,040,731 B | system `libva`, `libva-drm` | none (static-pie) |
| `aarch64-unknown-linux-musl` | 18,561,352 B | 9,571,783 B | system `libva`, `libva-drm`, `libatomic` | none (static-pie) |

Consumers:

```sh
# Player: pin ffmpeg-sdk.lock.json to the release, then
scripts/fetch-ffmpeg-sdk.sh aarch64-apple-darwin
scripts/release.sh
# usr: installs or repairs the tools pair from the newest release in releases.atom
sh dl ffmpeg
```

Player `v0.42.1` is the first Player release linked against this SDK. `usr` installs `tools` by default on Darwin arm64, Linux x86-64, and Linux arm64.

Supported `tools` workflows: ffprobe JSON; yt-dlp merge of h264/hevc/vp9/av1 video with aac/opus audio into mp4; `--convert-subs srt`; `--embed-metadata` with chapters; `--embed-thumbnail` (webp to png, png/jpeg as `attached_pic`); m4a/webm/mp3 metadata; mkv/ts remux to mp4 with `mov_text`; and on macOS the `encode` HEVC (`hevc_videotoolbox`) + AAC (`aac_at`) + `mov_text` command.

Intentional limitations: no network protocols (yt-dlp downloads), no devices, no `ffplay`, no encoders beyond PNG, SubRip, `mov_text`, and the two macOS AudioToolbox/VideoToolbox encoders; Linux has no HEVC encoder, so `encode` is macOS-only. x86-64 Linux is built and qualified only on GitHub's native runners.

## Guarantees added after `20261104`

- `release.yml` cuts releases only from `main`, and `prepare` refuses an existing release before the build matrix runs.
- Tags must be real dates: `resolve_release.py` and `build.py package` reject `YYYYMMDD` values that are not calendar dates.
- `build.py` fails if `git rev-parse HEAD` is not a commit hash. `audit` and `qualify` require one in the manifest, and `assemble_release.py` rejects an archive whose manifest commit is not `GITHUB_SHA`.

The `20261104` archives already carry commit `d611d42`, the release commit, so they meet these checks.
