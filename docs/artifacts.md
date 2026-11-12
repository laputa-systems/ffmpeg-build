# Artifacts

Each release publishes ten archives, each with a `.manifest.json`, plus `SHA256SUMS`: three targets for each of the three profiles, and the test-only `ffmpeg-fixtures` archive for `x86_64-unknown-linux-musl`.

The `fixtures` archive is a GPL generator for Play's fixture gate, not a runtime. See `docs/fixtures.md`.

## Names

```text
ffmpeg-<profile>-<version>-<target>.tar.xz
ffmpeg-<profile>-<version>-<target>.manifest.json
```

- `ffmpeg-<profile>` is the product: `ffmpeg-runtime`, `ffmpeg-play-sdk`, `ffmpeg-tools`, or the test-only `ffmpeg-fixtures`. `runtime` replaces the other two once their consumers switch.
- `<version>` is the FFmpeg version from `sources.lock.json`, for example `9.0.2`.
- `<target>` is `aarch64-apple-darwin`, `x86_64-unknown-linux-musl`, or `aarch64-unknown-linux-musl`.

The archive has a single top-level directory, named like the file without `.tar.xz`.

The `.manifest.json` beside each archive holds `schema_version` (1), `product`, `version`, `target`, `source_revision` (the commit the stage was built from), and `sources_lock_sha256`. Releases are tagged `release-<commit>`, so the file names carry no date.

## Layout

`runtime` (Linux names; see below for macOS):

```text
bin/ffmpeg                        RUNPATH $ORIGIN/../lib
bin/ffprobe
include/                          FFmpeg headers only
lib/libavcodec.so.63.1.102        SONAME libavcodec.so.63, RUNPATH $ORIGIN
lib/libavcodec.so.63 -> libavcodec.so.63.1.102
lib/libavcodec.so    -> libavcodec.so.63.1.102
                                  likewise libavdevice (63), libavformat (63), libavfilter (12),
                                  libavutil (61), libswresample (7), libswscale (10)
lib/pkgconfig/*.pc                the seven libraries; prefix=${pcfiledir}/../..; empty Libs.private
share/ffmpeg-build/manifest.json
share/licenses/{ffmpeg,dav1d,zlib}/
README
```

On macOS the libraries are `lib/libavcodec.63.1.102.dylib` with install name `@rpath/libavcodec.63.dylib`, and the links are `lib/libavcodec.63.dylib` and `lib/libavcodec.dylib`. Programs carry `LC_RPATH @loader_path/../lib` and libraries `LC_RPATH @loader_path`. The version numbers come from FFmpeg 9.0.2's headers; the manifest `libraries` key is authoritative. Symlinks occur only directly in `lib/`, name a sibling file, and resolve to a regular file. dav1d and zlib are linked into the libraries, not shipped. See `docs/runtime.md`.

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

`share/licenses/ffmpeg/` holds `LICENSE.md`, `CREDITS`, and `COPYING.LGPLv2.1`, plus `COPYING.GPLv2` for the GPL `runtime` and `tools` profiles.

SDK archives keep their symbols. Tools and runtime executables and runtime libraries are stripped, and on macOS ad-hoc signed after stripping. Today `usr` installs only the tools archive and never installs headers or libraries; consumers move to `runtime` separately.

## Manifest

`share/ffmpeg-build/manifest.json` is generated from `config_components.h`, `ffbuild/config.mak`, and `config.h`. Its keys:

| Key | Meaning |
| --- | --- |
| `contract` | `1` |
| `profile`, `target` | as in the archive name |
| `release` | `{archive}`, written by `package` |
| `sources` | version, URL, and SHA-256 of FFmpeg, dav1d, and zlib |
| `producer` | repository and commit |
| `configure_args`, `configure` | requested arguments and FFmpeg's recorded configuration |
| `components` | every resolved component by category; input and output devices are `indevs` and `outdevs`, and `lavfi` is the only one ever enabled |
| `requested_components`, `auto_selected` | the profile's request, and what configure added |
| `external_libraries` | FFmpeg `CONFIG_LIB*` libraries (`dav1d`) |
| `bundled_dependencies` | static libraries shipped or linked in (`dav1d`, `zlib`) |
| `frameworks`, `system_libraries` | what a consumer links from the system |
| `toolchain` | `cc`, SDK and sysroot, deployment target, CPU baseline, host, and musl version |
| `license` | FFmpeg's `FFMPEG_LICENSE`, set by the profile's `license` key: `GPL version 2 or later` for `runtime` and `tools`, `LGPL version 2.1 or later` for `play-sdk` |
| `libraries` | `runtime` only; see below |

`libraries` maps each of `libavcodec`, `libavdevice`, `libavfilter`, `libavformat`, `libavutil`, `libswresample`, and `libswscale` to:

| Key | Meaning |
| --- | --- |
| `file` | the regular file, relative to the archive root, for example `lib/libavcodec.so.63.1.102` |
| `links` | the symlinks that resolve to it, sorted, for example `["lib/libavcodec.so", "lib/libavcodec.so.63"]` |
| `soname` (Linux) | `DT_SONAME`, for example `libavcodec.so.63` |
| `install_name` (macOS) | `LC_ID_DYLIB`, for example `@rpath/libavcodec.63.dylib` |
| `sha256` | SHA-256 of `file` as shipped |

## Relocation

Nothing in an artifact contains the absolute build root. FFmpeg is configured with `--prefix=/opt/ffmpeg-build` and installed with `DESTDIR`. Dependency paths are passed relative to the build directory, so FFmpeg's baked configuration string carries no build path. Compiler, assembler, and Objective-C flags include `-ffile-prefix-map=<root>=.`, so debug info and `__FILE__` hold `./.work/...` relative paths. The SDK and runtime `.pc` files are rewritten to `prefix=${pcfiledir}/../..`; a consumer that installs the tree elsewhere can keep them as they are or replace that one line. Runtime `.pc` files also drop `Libs.private`, which only static linking reads. Runtime programs and libraries locate each other only through `$ORIGIN` or `@loader_path`; the only absolute paths left in them are the musl interpreter `/lib/ld-musl-<arch>.so.1`, system library and framework paths, and FFmpeg's compiled-in `/opt/ffmpeg-build` prefix, which appears in the configuration string and as the `-vpre` preset directory (`share/ffmpeg`, not shipped), as in `tools`. `audit` scans every staged file for the build root, and `qualify` scans every extracted file for an absolute `.work/build` or `.work/stage` path.

## Package and qualify

```sh
python3 build.py package --target aarch64-apple-darwin --profile play-sdk
python3 build.py package --target aarch64-apple-darwin --profile tools
python3 build.py package --target aarch64-apple-darwin --profile runtime
python3 build.py qualify --archive dist/ffmpeg-play-sdk-9.0.2-aarch64-apple-darwin.tar.xz
python3 build.py qualify --archive dist/ffmpeg-tools-9.0.2-aarch64-apple-darwin.tar.xz
python3 build.py qualify --archive dist/ffmpeg-runtime-9.0.2-aarch64-apple-darwin.tar.xz
scripts/linux-qualify.sh dist/ffmpeg-play-sdk-9.0.2-x86_64-unknown-linux-musl.tar.xz
make build verify TARGET=aarch64-apple-darwin
```

`package` reads only the stage, and it runs on any host. It writes the archive with Python `tarfile`. Entries are sorted, owned by uid and gid 0 with no user or group names, and have mtime 0. Directories are mode 0755, executables 0755, symlinks 0777, and other files 0644. `package` fails on any symlink in an SDK or tools stage, and on any runtime symlink that is outside `lib/`, has an absolute target or a target containing `/`, dangles, or loops. The xz stream has no timestamp or file name, so the same stage always gives the same bytes. `package` also writes the `.manifest.json` beside the archive.

`qualify` must run on the target platform. On Linux, `scripts/linux-qualify.sh` runs it in the `build` image for SDK and runtime archives and the `runtime` image for tools. It checks:

- the archive members: normalized, inside the root, files, directories, and symlinks that follow the `package` rules;
- extraction into `.work/tmp/qualify/<name>/path with spaces/`;
- the manifest: contract keys; profile, target, version, and release agree with the name; sources agree with the lock;
- the README, the licenses, and the absence of absolute build-tree paths;
- for `runtime`, that every manifest `libraries` entry matches the extracted file's SHA-256 and that its links resolve to it.

Then it runs a per-profile script:

- `tests/qualify-sdk.sh`: `pkg-config --static` resolves only paths inside the prefix (and the system `libva` on Linux). It links `tests/sdk-consumer.c` through `eval` so the escaped spaces survive. The consumer checks that `file` is the only protocol and decodes h264 natively and AV1 through the bundled `libdav1d`. It must link only system libraries: on macOS, `/usr/lib` and system frameworks; on Linux, musl libc, `libva`, `libva-drm`, and `libatomic`.
- `tests/qualify-tools.sh`: runs `tests/tools-workflows.sh` against the extracted pair, and on macOS checks that the `encode` encoders are present.
- `tests/qualify-runtime.sh`: runs `tests/tools-workflows.sh` against the extracted programs, then links `tests/sdk-consumer.c` with plain `pkg-config --cflags --libs` and an rpath into the prefix. The consumer allows `file`, `pipe`, and `fd`, decodes h264 and AV1 through the linked-in dav1d, and may depend only on libav* and the C library. On macOS it also checks the `encode` encoders.
