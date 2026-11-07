# ffmpeg-build

Producer repository for the pinned FFmpeg sources, profiles, builds, audits, and releases consumed by `play` and `usr`.

## Commands

```sh
python3 build.py fetch --target aarch64-apple-darwin --profile runtime
python3 build.py build --target aarch64-apple-darwin --profile runtime
python3 build.py audit --target aarch64-apple-darwin --profile runtime
scripts/linux-build.sh x86_64-unknown-linux-musl runtime
python3 -m unittest discover -s tests
```

## Invariants

- Build only from `sources.lock.json`; every source has a URL and SHA-256.
- The profile is the authoritative component list. Do not add a component without a named workflow that fails without it.
- `runtime` is exactly the union of `tools` and `play-sdk` per target, built shared: no network protocols or `ffplay`, and the virtual `lavfi` input is the only device.
- `play-sdk` has no programs, encoders, muxers, devices, or network protocols.
- `tools` has no network protocols or `ffplay`, and the virtual `lavfi` input is the only device.
- Each profile declares `license`: `tools` and `runtime` are `gpl` (GPL version 2 or later, needed for `cropdetect`), `play-sdk` is `lgpl`. Nonfree and version-3 code are never enabled.
- Artifacts are relocatable and contain no absolute build prefix. `play-sdk` and `tools` are static. `runtime` ships shared libav* only: dav1d and zlib are linked in, programs and libraries find each other only through `$ORIGIN` or `@loader_path` (macOS install names are `@rpath`), and Linux `NEEDED` is limited to libav*, musl libc, `libva`, and `libva-drm`.
- Archive symlinks exist only in `runtime`, directly in `lib/`, as sibling names that resolve to a regular file.
- Keep scratch under `.work/`, never `/tmp` or `$TMPDIR`. Set `TMPDIR=.work/tmp` for commands that spill files.
- Do not run formatters.
