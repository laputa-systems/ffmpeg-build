# ffmpeg-build

This repository owns the custom FFmpeg sources, pins, profiles, codec recipes, packaging, audits, and releases. `play` consumes the `play-sdk` archive through a pin; `usr` installs the `tools` archive.

## Layout

- `sources.lock.json` — upstream URLs, versions, and SHA-256 pins.
- `profiles/` — the authoritative component and platform configuration for `play-sdk` and `tools`.
- `build.py` — fetch, build, and audit controller; packaging and qualification follow in S5.
- `docs/` — baseline evidence and profile/artifact documentation.
- `.work/` — disposable downloads, builds, stages, and scratch (ignored locally).

## Build one target and profile

```sh
python3 build.py fetch --target aarch64-apple-darwin --profile play-sdk
python3 build.py build --target aarch64-apple-darwin --profile play-sdk
python3 build.py audit --target aarch64-apple-darwin --profile play-sdk
```

Sources are cached under `.work/cache/sources`; every cached and fresh download is verified against `sources.lock.json`. Build trees live at `.work/build/<target>/<profile>` and installed trees at `.work/stage/<target>/<profile>`.

The `play-sdk` profile is a static SDK: headers, static libraries, pkg-config files, and a generated manifest. The `tools` profile produces the `ffmpeg`/`ffprobe` pair. Neither profile enables network protocols, devices, or encoders unless its profile explicitly names them.

## Current scope

S0 and S1 establish the baseline, the source pins, both profile files, and the macOS `aarch64-apple-darwin` `play-sdk` build and audit. Linux targets and the `tools` component set follow in S2-S4.
