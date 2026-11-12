# ffmpeg-build

This repository owns the custom FFmpeg sources, pins, profiles, codec recipes, packaging, audits, and releases. The `runtime` archive is the shared FFmpeg (`ffmpeg`, `ffprobe`, libav* shared libraries, headers, pkg-config) that Player, `usr`, and Laputa packages move to. Until they do, `play` consumes the `play-sdk` archive through a pin and `usr` installs the `tools` archive.

## Layout

- `sources.lock.json` — upstream URLs, versions, and SHA-256 pins (`schema_version` 1, an `inputs` list).
- `Makefile` — `fetch`, `build`, `package`, `verify`, `lint`, `test`, and `clean` for one `TARGET`.
- `profiles/` — the authoritative component and platform configuration for `runtime`, `play-sdk`, and `tools`, plus the test-only `fixtures` generator.
- `build.py` — `fetch`, `build`, `audit`, `package`, and `qualify`.
- `scripts/` — Linux container builds and qualification in the pinned Alpine image (`docker/Dockerfile`).
- `tests/` — unit tests, tools workflows, the `encode` command, runtime, SDK, and tools qualification, and fixture generation.
- `docs/` — baseline evidence and profile/artifact documentation.
- `.work/` — disposable downloads, builds, stages, and scratch (ignored locally).

## Build one target and profile

`make build TARGET=<triple>` builds, audits, and packages every profile for the target, and `make verify TARGET=<triple>` qualifies the archives in `dist/`. `TARGET` defaults to the host's triple. The individual steps:

```sh
python3 build.py build --target aarch64-apple-darwin --profile play-sdk
python3 build.py audit --target aarch64-apple-darwin --profile play-sdk
python3 build.py package --target aarch64-apple-darwin --profile play-sdk
python3 build.py qualify --archive dist/ffmpeg-play-sdk-9.0.2-aarch64-apple-darwin.tar.xz

python3 build.py build --target aarch64-apple-darwin --profile runtime
python3 build.py audit --target aarch64-apple-darwin --profile runtime

scripts/linux-build.sh x86_64-unknown-linux-musl runtime
python3 build.py package --target x86_64-unknown-linux-musl --profile runtime
scripts/linux-qualify.sh dist/ffmpeg-runtime-9.0.2-x86_64-unknown-linux-musl.tar.xz

scripts/linux-build.sh x86_64-unknown-linux-musl tools
python3 build.py package --target x86_64-unknown-linux-musl --profile tools
scripts/linux-qualify.sh dist/ffmpeg-tools-9.0.2-x86_64-unknown-linux-musl.tar.xz

scripts/linux-build.sh x86_64-unknown-linux-musl fixtures
```

Targets are `aarch64-apple-darwin`, `x86_64-unknown-linux-musl`, and `aarch64-unknown-linux-musl`. Each builds natively: macOS on the host, Linux in a `linux/amd64` or `linux/arm64` container. Sources are cached under `.work/cache/sources` and verified against `sources.lock.json` on every use. Build trees live at `.work/build/<target>/<profile>` and stages at `.work/stage/<target>/<profile>`.

`runtime` is the union of the other two profiles built once as shared libraries: `ffmpeg`, `ffprobe`, and libav* that find each other through `$ORIGIN` or `@loader_path`, with dav1d and zlib linked in, GPL, and no network protocols or `ffplay`; the virtual `lavfi` input is its only device. `play-sdk` is a static playback SDK with no programs, encoders, muxers, devices, or network protocols. `tools` is the static, headless, GPL `ffmpeg`/`ffprobe` pair, with no network protocols or `ffplay`, and `lavfi` as its only device. `play-sdk` stays LGPL. The `fixtures` profile is test-only, GPL, and Linux `x86_64` only: static `ffmpeg`/`ffprobe` with the six external encoders Play's fixture generator needs. It is released only as the `ffmpeg-fixtures-<version>-x86_64-unknown-linux-musl.tar.xz` archive for generating test data, is not a runtime, and `build.py` rejects any other target. See `docs/runtime.md`, `docs/play-sdk.md`, `docs/tools-profile.md`, `docs/fixtures.md`, `docs/artifacts.md`, and `docs/release.md`.

Releases publish one `ffmpeg-<profile>-<version>-<target>.tar.xz` and `.manifest.json` per profile and target, tagged `release-<commit>` (see `docs/release.md`). Lint: `make lint`. Tests: `make test` or `python3 -m unittest discover -s tests`. Fixtures for the workflow tests come from `tests/fixtures/gen.sh .work/fixtures`, which needs a full host FFmpeg 9.0.2, or from `scripts/linux-fixtures.sh`.
