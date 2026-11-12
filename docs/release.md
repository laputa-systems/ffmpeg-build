# Release

Releases are produced only by `.github/workflows/release.yml`. The workflow runs the same commands as a local build: `make build` and `make verify`.

## Publish

```sh
git push origin main
gh workflow run release.yml
gh run watch
gh release view "release-$(git rev-parse HEAD)" --json tagName,isPrerelease,assets
```

The workflow runs only on `workflow_dispatch` from the default branch. The tag is `release-<commit>`: the `publish` job refuses to run when that tag exists, creates it at the triggering commit through the GitHub API, and passes `--verify-tag` to `gh release create`. A release is never overwritten and no job moves a tag or replaces an asset. To publish again, push a new commit.

Releases are pre-releases. Consumers enumerate `https://github.com/laputa-systems/ffmpeg-build/releases.atom` rather than `/releases/latest`.

## Jobs

| Job | Runner | Does |
| --- | --- | --- |
| `preflight` | `ubuntu-26.04-arm` | rejects any ref other than the default branch, reads the FFmpeg version from `sources.lock.json`, runs `python3 -m unittest discover -s tests` |
| `fixtures` | `ubuntu-26.04` | `scripts/linux-fixtures.sh`: test fixtures from Alpine FFmpeg 9.0.2 |
| `build` | `xcode-27` (Xcode 27.1), `ubuntu-26.04`, `ubuntu-26.04-arm` | `make build TARGET=<triple>`: `build`, `audit`, and `package` for every profile (Linux in the digest-pinned Alpine image, plus `fixtures` on x86-64); on macOS also `tests/tools-workflows.sh` on the tools and runtime stages |
| `assemble` | `ubuntu-26.04-arm` | `.github/scripts/assemble_release.py`: exactly ten archives and ten manifests, each manifest checked against the commit and the SHA-256 of `sources.lock.json`, and a sorted `SHA256SUMS` |
| `verify` | `xcode-27`, `ubuntu-26.04`, `ubuntu-26.04-arm` | `sha256sum -c` (`shasum -a 256 -c` on macOS), then `make verify TARGET=<triple>` on the assembled bytes |
| `publish` | `ubuntu-26.04-arm` | the only job with `contents: write`; rechecks the ref, creates the tag, writes the release notes, creates the pre-release, and compares the published `SHA256SUMS` |

Every action is pinned to a full commit SHA. The Alpine images are pinned by digest in `docker/Dockerfile`, the same digests `python-build` uses. The only cache holds verified source tarballs and the pinned `laputa-buildlib` wheel. Its key covers the source lock, the profiles, `build.py`, the scripts, the Dockerfile, the target, and the runner.

## Assets

- Ten archives: `ffmpeg-<profile>-<version>-<target>.tar.xz` for the three targets and the `runtime`, `play-sdk`, and `tools` profiles, plus `ffmpeg-fixtures-<version>-x86_64-unknown-linux-musl.tar.xz`, qualified by `tests/qualify-fixtures.sh`. See `docs/artifacts.md`.
- Ten manifests: `ffmpeg-<profile>-<version>-<target>.manifest.json` with `schema_version`, `product`, `version`, `target`, `source_revision`, and `sources_lock_sha256`.
- `SHA256SUMS`: one line per archive and manifest, sorted by file name.

## Consumers

The `play` Linux image downloads the `ffmpeg-fixtures` archive for `x86_64-unknown-linux-musl`. After the first release in this format, `play` must point at the `release-<commit>` tag, the `ffmpeg-fixtures-<version>-x86_64-unknown-linux-musl.tar.xz` asset, and its new SHA-256 from `SHA256SUMS`, and extract it with `tar -xJf`. The archive root directory is now `ffmpeg-fixtures-<version>-x86_64-unknown-linux-musl`; `--strip-components=1` still applies.

## Update FFmpeg

1. Change `sources.lock.json`: version, URL, filename, archive root, and the real SHA-256.
2. Run the local matrix: `make build verify` for each target, `tests/tools-workflows.sh`, and `tests/encode-command.sh`.
3. Dispatch the release workflow from `main`.
4. Update `play/ffmpeg-sdk.lock.json` with the new tag and the published SHA-256 values. Rebuild and qualify Player, and publish a Player patch release.
5. `usr` discovers the new tools release from `releases.atom`.

Never point a consumer at a tag before its release and checksums exist.

## Last date-tagged release: `20261104`

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

Intentional limitations: no network protocols (yt-dlp downloads), no devices beyond the virtual `lavfi` input, no `ffplay`, no encoders beyond PNG, SubRip, `mov_text`, and the two macOS AudioToolbox/VideoToolbox encoders; Linux has no HEVC encoder, so `encode` is macOS-only. x86-64 Linux is built and qualified only on GitHub's native runners.

## Guarantees

- `release.yml` cuts releases only from the default branch, and `publish` refuses an existing `release-<commit>` tag before it creates one.
- `build.py` fails if `git rev-parse HEAD` is not a commit hash. `audit` and `qualify` require one in the manifest, and `assemble_release.py` rejects an archive or manifest whose commit is not `GITHUB_SHA`, and a manifest whose `sources_lock_sha256` is not the digest of `sources.lock.json` at that commit.
