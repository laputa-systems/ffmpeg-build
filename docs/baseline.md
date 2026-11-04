# Baseline

Evidence captured at the S0 checkpoint on 2026-11-04 from this host and checkout. This is a comparison point, not a history log.

## Checkouts

```sh
git -C /Users/josh/d/ffmpeg-build status --short
git -C /Users/josh/d/play rev-parse HEAD
git -C /Users/josh/usr rev-parse HEAD
git -C /Users/josh/d/python-build rev-parse HEAD
git -C /Users/josh/d/ffmpeg-build remote -v
```

| Repository | HEAD | Notes |
| --- | --- | --- |
| `~/d/play` | `3bf9b42d41436d9ada0bb471603703903cf6f811` | `docs/metrics.md` row only beyond the `da0c70dbde2b` release commit |
| `~/usr` | `864a2e55ded16517b310d31cdc9d188e952fb8e4` | one commit ahead of origin; preserve it |
| `~/d/python-build` | `f1a5f743eb23414fed6ea8a4dcc873bfb7c73822` | unchanged |
| `~/d/ffmpeg-build` | `d53abd1` plus this slice | remote `laputa-systems/ffmpeg-build`, public |

## Source pins

| Source | Version | URL | SHA-256 |
| --- | --- | --- | --- |
| FFmpeg | 9.0.2 (`n9.0.2`, commit `ce8f11b9fac4cd7ccfb41ca7c01bc17f5cda8cc3`) | `https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n9.0.2.tar.gz` | `6e374ed621e48faa40639307dff48ba6fe574a509977956d2cce9669b7cc27e9` |
| dav1d | 1.5.4 | `https://code.videolan.org/videolan/dav1d/-/archive/1.5.4/dav1d-1.5.4.tar.bz2` | `2abfb0c89212e6e4733a54e0ae509ec00a5b845a6360946f918806e14aedb011` |
| zlib | 1.3.2 | `https://github.com/madler/zlib/releases/download/v1.3.2/zlib-1.3.2.tar.xz` | `d7a0654783a4da529d1bb793b7ad9c3318020af77667bcae35f95d0e42a792f3` |

The pins match `play/scripts/build-ffmpeg.sh`, `play/scripts/build-deps.sh`, and `play/scripts/build-deps-linux.sh` at Player HEAD. `build.py fetch` verifies each archive before extraction and again on every cached use.

## Player comparison numbers

Recorded in `play/docs/metrics.md` at Player `da0c70dbde2b` and carried into `3bf9b42`:

| Platform | Distributable | Closure | Files | Protocols |
| --- | ---: | ---: | ---: | ---: |
| macOS release, stripped | 7,107,568 B | 12,606,880 B | 8 | 1 (`file`) |
| Linux release, stripped | 23,820,624 B | — | — | 1 (`file`), 7 `NEEDED` entries |

Player gates at that revision: corpus 104/0, audio 15/0, hwdec 8/0, seek 5/0, FFmpeg audit 19/0. The budget is 29,542,136 B.

## Local artifact state

```sh
test -e /Users/josh/d/play/.work/deps/release/ffmpeg/lib/libavcodec.a
test -e /Users/josh/d/play/dist/Player.app
```

`play/.work/deps` is empty, so the recorded Player gates were not re-run from a local source build; the release numbers above are the comparison point. `play/dist/Player.app` exists but was not used as evidence. A missing build tree is not a red test. The producer build and audit in S1 establish the replacement evidence.

## S0 checks

```sh
git check-ignore -q .work
jaq -e . sources.lock.json profiles/play-sdk.json profiles/tools.json
git status --short
```

Results: `.work/` is ignored through `.git/info/exclude`, all three JSON files parse, and only the intended S0 files are untracked or modified. No source pin lacks a SHA-256 and both profiles declare their target scope.
