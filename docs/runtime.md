# runtime

`profiles/runtime.json` builds one shared FFmpeg per target: `ffmpeg`, `ffprobe`, the seven FFmpeg shared libraries (libavcodec, libavdevice, libavfilter, libavformat, libavutil, libswresample, libswscale), their headers, and pkg-config files. Player links these libraries, `usr` installs the programs with them, and Laputa packages ship the same tree. It replaces `play-sdk` and `tools`, which keep building until every consumer has switched.

## Commands

```sh
python3 build.py build --target aarch64-apple-darwin --profile runtime
python3 build.py audit --target aarch64-apple-darwin --profile runtime
python3 build.py package --target aarch64-apple-darwin --profile runtime
python3 build.py qualify --archive dist/ffmpeg-runtime-9.0.2-aarch64-apple-darwin.tar.xz

scripts/linux-build.sh x86_64-unknown-linux-musl runtime
python3 build.py package --target x86_64-unknown-linux-musl --profile runtime
scripts/linux-qualify.sh dist/ffmpeg-runtime-9.0.2-x86_64-unknown-linux-musl.tar.xz
```

On Linux, `scripts/linux-build.sh` runs `build` and `audit` in the `build` image, then copies the stage out and runs `tests/tools-workflows.sh` in the `runtime-libva` image: a clean Alpine with `bash`, `file`, `python3`, and the system `libva`, with the prefix mounted read-only and no `/work`. `scripts/linux-qualify.sh` qualifies runtime archives in the `build` image, because the consumer check needs a compiler.

## Components

The component set is exactly the union of `tools` and `play-sdk` for each target; `tests/test_build.py` fails if they drift apart. Each component's workflow is documented in `docs/tools-profile.md` or `docs/play-sdk.md`.

| Target | Platform flags | Hardware | Frameworks or system libraries |
| --- | --- | --- | --- |
| `aarch64-apple-darwin` | `--enable-videotoolbox --enable-audiotoolbox` | `h264_videotoolbox`, `hevc_videotoolbox` hwaccels; `hevc_videotoolbox`, `aac_at` encoders | VideoToolbox, AudioToolbox, CoreFoundation, CoreMedia, CoreVideo, CoreServices |
| `x86_64-unknown-linux-musl` | `--enable-vaapi` | `h264_vaapi`, `hevc_vaapi`, `vp9_vaapi`, `av1_vaapi` hwaccels; native `av1` decoder | system `libva`, `libva-drm` |
| `aarch64-unknown-linux-musl` | `--enable-vaapi` | as x86-64 | system `libva`, `libva-drm` |

Protocols are `file`, `pipe`, and `fd`. Configure runs with `--disable-network`, `--disable-autodetect`, `--disable-everything`, and `--enable-gpl`; `ffplay` is never built. libavdevice is built only for the virtual `lavfi` input device (`-f lavfi`), and every other input and output device stays off. The runtime is GPL version 2 or later because `cropdetect` depends on GPL; the manifest `license` says so, and `share/licenses/ffmpeg/` ships `COPYING.GPLv2` with `COPYING.LGPLv2.1`.

## Linkage

Configure uses `--enable-shared --disable-static`. dav1d and zlib build from `sources.lock.json` as static, position-independent archives in `.work/build/<target>/runtime/deps` and link into libavcodec and libavformat. FFmpeg's version scripts keep their symbols local, so the closure a consumer sees is only libav*.

| | Linux | macOS |
| --- | --- | --- |
| library identity | SONAME `libavcodec.so.63` | install name `@rpath/libavcodec.63.dylib` |
| programs find `lib/` through | `DT_RUNPATH` `$ORIGIN/../lib` | `LC_RPATH` `@loader_path/../lib` |
| libraries find each other through | `DT_RUNPATH` `$ORIGIN` | `LC_RPATH` `@loader_path` |
| other dependencies | musl `libc.musl-<arch>.so.1`, `libva.so.2`, `libva-drm.so.2` | `/usr/lib/libSystem.B.dylib` and the frameworks above |
| program interpreter | `/lib/ld-musl-<arch>.so.1` | dyld |

On Linux, `$ORIGIN` reaches the linker through response files in the build directory (`ld-program.rsp`, `ld-library.rsp`), because FFmpeg's makefiles expand dollar signs in the link flags. Programs and libraries carry a 2 MiB `PT_GNU_STACK`: musl takes its default thread stack from the main program and the libraries loaded at startup, and FFmpeg's threads overflow musl's 128 KiB default. Libraries are stripped by the FFmpeg install step, programs by `build.py`; on macOS every program and library is ad-hoc signed after stripping.

Consumers on Linux need the system `libva` and `libva-drm` (Alpine package `libva`), because libavutil links VA-API directly. Nothing else outside the archive is required.

## Audit

`audit` checks the shared configuration (`CONFIG_SHARED=yes`, no `CONFIG_STATIC`), then every program and library:

- Linux: ELF machine and kind; `NEEDED` limited to libav* siblings, musl libc, `libva.so.2`, and `libva-drm.so.2` (so no `libgcc_s`, `libstdc++`, `libz`, or `libdav1d`); `RUNPATH` exactly `$ORIGIN/../lib` or `$ORIGIN`; no `RPATH`; no text relocations; 2 MiB `PT_GNU_STACK`; the musl interpreter; no `GLIBC_` versions.
- macOS: Mach-O arm64 kind; load commands limited to libav* siblings by `@rpath`, `/usr/lib` (no `libz`), and the profile frameworks; `LC_RPATH` exactly `@loader_path/../lib` or `@loader_path`; a valid code signature.
- Libraries export no dav1d or zlib symbols, and each SONAME or install name is `@rpath/<library>.<major>.dylib` or `<library>.so.<major>`.
- `lib/` holds exactly the seven versioned libraries and their two links each; every symlink is a sibling name inside `lib/` that resolves to a regular file.
- The seven `.pc` files have `prefix=${pcfiledir}/../..`, an empty `Libs.private`, and no absolute path.
- No dav1d or zlib headers ship.
- The staged `ffmpeg` runs from the stage, and `-protocols`, `-encoders`, and `-hwaccels` report exactly the profile's protocols, encoders, and hardware type (`vaapi` or `videotoolbox`).
- The manifest `libraries` entry matches the stage byte for byte.

`qualify` (through `tests/qualify-runtime.sh`) runs `tests/tools-workflows.sh` against the extracted prefix, checks that `pkg-config` resolves only the prefix and the seven `-l` flags, links `tests/sdk-consumer.c` against the shared libraries with an rpath into a path containing spaces, decodes h264 and AV1 (through the linked-in dav1d), and checks that the consumer's own dependencies are only libav* and the C library. On macOS it also checks the `encode` encoders.
