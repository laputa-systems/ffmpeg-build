# ffmpeg-build

Producer repository for the pinned FFmpeg sources, profiles, builds, audits, and releases consumed by `play` and `usr`.

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
- Artifacts are relocatable and contain no absolute build prefix. `play-sdk` and `tools` are static. `runtime` ships shared libav* only: dav1d and zlib are linked in, programs and libraries find each other only through `$ORIGIN` or `@loader_path` (macOS install names are `@rpath`), and Linux `NEEDED` is limited to libav*, musl libc, `libva`, and `libva-drm`.
- Archive symlinks exist only in `runtime`, directly in `lib/`, as sibling names that resolve to a regular file.
- Keep scratch under `.work/`, never `/tmp` or `$TMPDIR`. Set `TMPDIR=.work/tmp` for commands that spill files.
- Releases are cut only by `.github/workflows/release.yml`, tagged `release-<commit>`; archives are `ffmpeg-<profile>-<version>-<target>.tar.xz` with a `.manifest.json`. See `docs/release.md`.
- Do not run formatters.

## Verification

- On macOS arm64, `make test`: cold 0.41s (created `.venv`), warm 0.28s; 73 tests each. `make lint`: first 0.57s, warm 0.12s (after test setup). Times are elapsed, not performance gates.
- `make coverage` runs the controller suite with branch instrumentation over the three first-party Python modules. It prints a summary and writes `.work/coverage/report.json`.
- For package and qualification edits, `uv run --frozen python -m unittest discover -s tests -p test_build.py -k qualify` checks a sealed tools archive, manifest and native-script handoff. `make test` adds controller and release assembly coverage. `make verify` requires native artifacts.
- `tests/test_cli.py` exercises the `build.py` version command, target rejection, and required package arguments through the process boundary. The Makefile and native Linux wrapper have separate usage paths.
- `sources.lock.json` and profile configuration consumed by the builder: `tests/test_build.py` (`ProfileTests`, `RuntimeProfileTests`, `LicenseAndDeviceTests`, `FixturesProfileTests`); verified local source acquisition and extraction: `SourceAcquisitionTests`. Upstream downloads and full builds run separately.
- Archive names, members, symlinks and release manifests consumed by `play` and `usr`: `tests/test_build.py` (`StageTests`, `SymlinkTests`, `RuntimeStageTests`) and `tests/test_assemble_release.py`; full artifact qualification is `make verify` after a build.
- `play` consumes the static SDK and fixture tools: `tests/qualify-sdk.sh`, `tests/sdk-consumer.c`, and `tests/qualify-fixtures.sh` exercise built artifacts, outside `make test`.
- `usr` consumes tools; runtime is intended for `play`, `usr`, and Laputa packages: `tests/qualify-tools.sh`, `tests/qualify-runtime.sh`, and `tests/tools-workflows.sh` exercise built artifacts, outside `make test`.
- No public Python API or server endpoint is declared. FFmpeg's shipped CLI and library behavior is covered only for the workflows above, not exhaustively.
- Performance workload: none established. Playback decoding and tool transcoding are user-visible hot paths; later runtime-affecting work needs representative target-specific workloads and a baseline before a performance gate.
