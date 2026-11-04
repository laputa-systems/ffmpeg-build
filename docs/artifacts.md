# Artifacts

Each release publishes six archives, plus `SHA256SUMS` and `release.json`.

## Names

```text
ffmpeg-<upstream>+<tag>-<target>-<profile>.tar.gz
```

- `<upstream>` is the FFmpeg version from `sources.lock.json`, for example `9.0.2`.
- `<tag>` is the producer release: `YYYYMMDD` for the first release of a UTC day, `YYYYMMDD-rN` for later revisions, or `local` for a local package.
- `<target>` is `aarch64-apple-darwin`, `x86_64-unknown-linux-musl`, or `aarch64-unknown-linux-musl`.
- `<profile>` is `play-sdk` or `tools`.

The archive has a single top-level directory, named like the file without `.tar.gz`.

## Layout

`play-sdk`:

```text
include/                          FFmpeg, dav1d, and zlib headers
lib/*.a                           libavcodec, libavformat, libavfilter, libavutil, libswresample, libswscale, libdav1d, libz
lib/pkgconfig/*.pc                prefix=${pcfiledir}/../..
share/ffmpeg-build/manifest.json
share/licenses/{ffmpeg,dav1d,zlib}/
README
```

`tools`:

```text
bin/ffmpeg
bin/ffprobe
share/ffmpeg-build/manifest.json
share/licenses/{ffmpeg,dav1d,zlib}/
README
```

SDK archives keep their symbols. Tools executables are stripped, and on macOS ad-hoc signed after stripping. `usr` installs only the tools archive. It never installs headers or libraries.

## Manifest

`share/ffmpeg-build/manifest.json` is generated from `config_components.h`, `ffbuild/config.mak`, and `config.h`. Its keys:

| Key | Meaning |
| --- | --- |
| `contract` | `1` |
| `profile`, `target` | as in the archive name |
| `release` | `{tag, archive}`, written by `package` |
| `sources` | version, URL, and SHA-256 of FFmpeg, dav1d, and zlib |
| `producer` | repository and commit |
| `configure_args`, `configure` | requested arguments and FFmpeg's recorded configuration |
| `components` | every resolved component by category |
| `requested_components`, `auto_selected` | the profile's request, and what configure added |
| `external_libraries` | FFmpeg `CONFIG_LIB*` libraries (`dav1d`) |
| `bundled_dependencies` | static libraries shipped or linked in (`dav1d`, `zlib`) |
| `frameworks`, `system_libraries` | what a consumer links from the system |
| `toolchain` | `cc`, SDK and sysroot, deployment target, CPU baseline, host, and musl version |
| `license` | `LGPL version 2.1 or later` |

## Relocation

Nothing in an artifact contains the absolute build root. FFmpeg is configured with `--prefix=/opt/ffmpeg-build` and installed with `DESTDIR`. Dependency paths are passed relative to the build directory, so FFmpeg's baked configuration string carries no build path. Compiler, assembler, and Objective-C flags include `-ffile-prefix-map=<root>=.`, so debug info and `__FILE__` hold `./.work/...` relative paths. The SDK `.pc` files are rewritten to `${pcfiledir}/../..`. `audit` scans every staged file for the build root, and `qualify` scans every extracted file for an absolute `.work/build` or `.work/stage` path.

## Package and qualify

```sh
python3 build.py package --target aarch64-apple-darwin --profile play-sdk --tag local
python3 build.py package --target aarch64-apple-darwin --profile tools --tag local
python3 build.py qualify --archive dist/ffmpeg-9.0.2+local-aarch64-apple-darwin-play-sdk.tar.gz
python3 build.py qualify --archive dist/ffmpeg-9.0.2+local-aarch64-apple-darwin-tools.tar.gz
scripts/linux-qualify.sh dist/ffmpeg-9.0.2+local-x86_64-unknown-linux-musl-play-sdk.tar.gz
```

`package` reads only the stage, and it runs on any host. It writes the archive with Python `tarfile`. Entries are sorted, owned by uid and gid 0 with no user or group names, and have mtime 0. Directories are mode 0755, executables 0755, and other files 0644. The gzip header has mtime 0 and no file name, so the same stage always gives the same bytes.

`qualify` must run on the target platform. On Linux, `scripts/linux-qualify.sh` runs it in the `build` image for SDKs and the `runtime` image for tools. It checks:

- the archive members: normalized, inside the root, files and directories only;
- extraction into `.work/tmp/qualify/<name>/path with spaces/`;
- the manifest: contract keys; profile, target, version, and release agree with the name; sources agree with the lock;
- the README, the licenses, and the absence of absolute build-tree paths.

Then it runs a per-profile script:

- `tests/qualify-sdk.sh`: `pkg-config --static` resolves only paths inside the prefix (and the system `libva` on Linux). It links `tests/sdk-consumer.c` through `eval` so the escaped spaces survive. The consumer checks that `file` is the only protocol and decodes h264 natively and AV1 through the bundled `libdav1d`. It must link only system libraries: on macOS, `/usr/lib` and system frameworks; on Linux, musl libc, `libva`, `libva-drm`, and `libatomic`.
- `tests/qualify-tools.sh`: runs `tests/tools-workflows.sh` against the extracted pair, and on macOS checks that the `encode` encoders are present.
