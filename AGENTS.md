# ffmpeg-build

Producer repository for the pinned FFmpeg sources, profiles, builds, audits, and releases consumed by `play` and `usr`.

## Commands

```sh
python3 build.py fetch --target aarch64-apple-darwin --profile play-sdk
python3 build.py build --target aarch64-apple-darwin --profile play-sdk
python3 build.py audit --target aarch64-apple-darwin --profile play-sdk
python3 -m unittest discover -s tests
```

## Invariants

- Build only from `sources.lock.json`; every source has a URL and SHA-256.
- The profile is the authoritative component list. Do not add a component without a named workflow that fails without it.
- `play-sdk` has no programs, encoders, muxers, devices, or network protocols.
- `tools` has no network protocols, devices, or `ffplay`.
- Artifacts are static, relocatable, and contain no absolute build prefix.
- Keep scratch under `.work/`, never `/tmp` or `$TMPDIR`. Set `TMPDIR=.work/tmp` for commands that spill files.
- Do not run formatters.
