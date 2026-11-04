# ffmpeg-build

This repository owns the custom FFmpeg sources, pins, profiles, codec recipes, packaging, audits, and releases. `play` consumes the `play-sdk` archive through a pin; `usr` installs the `tools` archive.

## Layout

- `sources.lock.json` — upstream URLs, versions, and SHA-256 pins.
- `profiles/` — the authoritative component and platform configuration for `play-sdk` and `tools`.
- `build.py` — `fetch`, `build`, `audit`, `package`, and `qualify`.
- `scripts/` — Linux container builds and qualification in the pinned Alpine image (`docker/Dockerfile`).
- `tests/` — unit tests, tools workflows, the `encode` command, SDK and tools qualification, and fixture generation.
- `docs/` — baseline evidence and profile/artifact documentation.
- `.work/` — disposable downloads, builds, stages, and scratch (ignored locally).

## Build one target and profile

```sh
python3 build.py build --target aarch64-apple-darwin --profile play-sdk
python3 build.py audit --target aarch64-apple-darwin --profile play-sdk
python3 build.py package --target aarch64-apple-darwin --profile play-sdk --tag local
python3 build.py qualify --archive dist/ffmpeg-9.0.2+local-aarch64-apple-darwin-play-sdk.tar.gz

scripts/linux-build.sh x86_64-unknown-linux-musl tools
python3 build.py package --target x86_64-unknown-linux-musl --profile tools --tag local
scripts/linux-qualify.sh dist/ffmpeg-9.0.2+local-x86_64-unknown-linux-musl-tools.tar.gz
```

Targets are `aarch64-apple-darwin`, `x86_64-unknown-linux-musl`, and `aarch64-unknown-linux-musl`. Each builds natively: macOS on the host, Linux in a `linux/amd64` or `linux/arm64` container. Sources are cached under `.work/cache/sources` and verified against `sources.lock.json` on every use. Build trees live at `.work/build/<target>/<profile>` and stages at `.work/stage/<target>/<profile>`.

`play-sdk` is a static playback SDK with no programs, encoders, muxers, devices, or network protocols. `tools` is the static, headless `ffmpeg`/`ffprobe` pair, with no network protocols, devices, or `ffplay`. See `docs/play-sdk.md`, `docs/tools-profile.md`, `docs/artifacts.md`, and `docs/release.md`.

Tests: `python3 -m unittest discover -s tests`. Fixtures for the workflow tests come from `tests/fixtures/gen.sh .work/fixtures`, which needs a full host FFmpeg 9.0.2, or from `scripts/linux-fixtures.sh`.
