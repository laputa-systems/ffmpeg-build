# ffmpeg-build

`make clean` removes the local release, build, and stage outputs.
It preserves installed dependencies and unrelated scratch files.

Producer repository for the pinned FFmpeg sources, profiles, builds, audits, and releases consumed by `play` and `usr`.

The roadmap, [docs/roadmap.md](docs/roadmap.md), holds all current and future work; its Status is the resume point.

## Commands

```sh
make build verify TARGET=aarch64-apple-darwin
make lint
make test
python3 build.py fetch --target aarch64-apple-darwin --profile runtime
python3 build.py build --target aarch64-apple-darwin --profile runtime
python3 build.py audit --target aarch64-apple-darwin --profile runtime
scripts/linux-build.sh x86_64-unknown-linux-musl runtime
scripts/linux-build.sh x86_64-unknown-linux-musl fixtures
python3 -m unittest discover -s tests
```

## Invariants

- `build.py` and `.github/scripts/assemble_release.py` import `laputa-buildlib` through `bootstrap.py`, which puts the wheel pinned in `sources.lock.json` on `sys.path` (fetched into `.work/cache/sources`); keep `pyproject.toml` and the lock on the same version.
- Build only from `sources.lock.json` (`schema_version` 1, an `inputs` list); every input has a name, version, URL, and SHA-256.
- The profile is the authoritative component list. Do not add a component without a named workflow that fails without it.
- `runtime` is exactly the union of `tools` and `play-sdk` per target, built shared: no network protocols or `ffplay`, and the virtual `lavfi` input is the only device.
- `play-sdk` has no programs, encoders, muxers, devices, or network protocols.
- `tools` has no network protocols or `ffplay`, and the virtual `lavfi` input is the only device.
- `fixtures` is test-only, GPL, and builds only `x86_64-unknown-linux-musl`: static `ffmpeg`/`ffprobe` with `libx264`, `libx265`, `libsvtav1`, `libvpx`, `libmp3lame`, and `libopus` for Play's fixture generator. It is released only as the `ffmpeg-fixtures-<version>-x86_64-unknown-linux-musl.tar.xz` archive for generating test data and is not a runtime.
- Each profile declares `license`: `tools` and `runtime` are `gpl` (GPL version 2 or later, needed for `cropdetect`), `fixtures` is `gpl` (its x264 and x265 encoders are GPLv2), `play-sdk` is `lgpl`. Nonfree and version-3 code are never enabled.
- Artifacts are relocatable and contain no absolute build prefix. `play-sdk` and `tools` are static. `runtime` ships shared libav* and, on Linux, bundled `libva.so.2` and `libva-drm.so.2`; dav1d, zlib, and Linux libdrm are linked in. Programs and libraries find each other only through `$ORIGIN` or `@loader_path` (macOS install names are `@rpath`), and Linux `NEEDED` is limited to these bundled libraries and musl libc.
- Archive symlinks exist only in `runtime`, directly in `lib/`, as sibling names that resolve to a regular file.
- Keep scratch under `.work/`, never `/tmp` or `$TMPDIR`. Set `TMPDIR=.work/tmp` for commands that spill files.
- Releases are cut only by `.github/workflows/release.yml`, tagged `release-<commit>`; archives are `ffmpeg-<profile>-<version>-<target>.tar.xz` with a `.manifest.json`. See `docs/release.md`.
- Do not run formatters.

## Verification

- On macOS ARM64, `make test` passed 168 controller tests in 5.54 seconds from a fresh clone and 3.30 seconds median across three warm runs. The native `make verify` suite separately checks actual artifacts after a build.
- `make coverage` instruments the controller and gate code and writes `.work/coverage/report.json`.
- `make mutants-diff` uses committed changes, locked tools and the configured critical scopes. The hosted lane runs it on both Linux architectures and macOS ARM64.
- For package and qualification edits, `uv run --frozen python -m unittest discover -s tests -p test_build.py -k qualify` checks a sealed tools archive, manifest and native-script handoff. `make test` adds controller and release assembly coverage. `make verify` requires native artifacts.
- `tests/test_cli.py` exercises the `build.py` version command, target rejection, and required package arguments through the process boundary. The Makefile and native Linux wrapper have separate usage paths.
- `sources.lock.json` and profile configuration consumed by the builder: `tests/test_build.py` (`ProfileTests`, `RuntimeProfileTests`, `LicenseAndDeviceTests`, `FixturesProfileTests`); verified local source acquisition and extraction: `SourceAcquisitionTests`. Upstream downloads and full builds run separately.
- Archive names, members, symlinks and release manifests consumed by `play` and `usr`: `tests/test_build.py` (`StageTests`, `SymlinkTests`, `RuntimeStageTests`) and `tests/test_assemble_release.py`; full artifact qualification is `make verify` after a build.
- `play` consumes the static SDK and fixture tools: `tests/qualify-sdk.sh`, `tests/sdk-consumer.c`, and `tests/qualify-fixtures.sh` exercise built artifacts, outside `make test`.
- `usr` consumes tools; runtime is intended for `play`, `usr`, and Laputa packages: `tests/qualify-tools.sh`, `tests/qualify-runtime.sh`, and `tests/tools-workflows.sh` exercise built artifacts, outside `make test`.
- No public Python API or server endpoint is declared. FFmpeg's shipped CLI and library behavior is covered only for the workflows above, not exhaustively.
- Performance workload: none established. Playback decoding and tool transcoding are user-visible hot paths; later runtime-affecting work needs representative target-specific workloads and a baseline before a performance gate.
