# Extract FFmpeg into `laputa-systems/ffmpeg-build`

## Status

**Goal.** Make `laputa-systems/ffmpeg-build` the one authoritative home for the custom FFmpeg sources, pins, profile configuration, codec recipes, packaging, audits, and releases. Player consumes a pinned `play-sdk`; `usr` installs the released `ffmpeg`/`ffprobe` pair.

**Accepted.** None. S0 is next.

**Red or parked.** None.

**Next.** S0: record the baseline, create the producer skeleton, and make `.work/` ignored before the first build.

**Resume.** Read this file and execute from S0. Stop only on a hard stop in the charter. First command: `git -C /Users/josh/d/ffmpeg-build status --short`.

## Charter

- One writer by default. S7 and S9 may run in parallel after S6 because they own disjoint repositories; S11 waits for S8, and S12 waits for S10 and S11. Worktrees live at `.work/wt/<lane>`, never `/tmp` or `$TMPDIR`; point `TMPDIR` at `.work/tmp`.
- Decide and keep going. Record a decision only when a later slice depends on it. Use the smallest reversible assumption when evidence is missing.
- Within the owner's grant, proceed without asking. The grant covers editing and pushing the three named repositories, creating the named tags and releases, running their workflows, downloading sources, building in Docker, and installing into scratch `HOME` roots under `.work/`.
- Hard stops, each parking the item: an irreversible or outside-repo action not named in the grant; a forbidden effect in **Execution boundary**; a loop that cannot check anything; a required GitHub runner or release asset that is unavailable.
- Parity before optimization. Do not upgrade FFmpeg, tune codecs, or shrink artifacts before extraction parity is accepted.
- Fix an egregiously slow or plainly broken thing met on the way, in its own commit, to a numeric threshold: a local command over 10 minutes when a narrower one exists, a build over 2× the recorded baseline without a named cause, or a test that hangs past its timeout. Record anything else and leave it.
- Every commit is a Conventional Commit with scope `producer`, `play`, `usr`, or `release`; the item ID goes in the body. Code comments never cite this file.
- Run the narrowest acceptance command. The full Player suite runs at S8 and S12. Do not run formatters. Do not push any repository or tag outside the grant.
- After each accepted slice, run the parent steering checkpoint from `orchestrate/references/campaigns.md`. Rewrite **Status** in place only when the ruling changes; never append a checkpoint, handoff, or log.
- A failing item gets three attempts, then parks on its branch with the cause and a retry condition. A shared environment blocker gets one owner.

## Decisions

### Owner-decided

- **D1 — Publication authority.** Push `laputa-systems/ffmpeg-build`, `joshuarli/play`, and `joshuarli/usr`; create the producer and Player tags/releases; run their workflows. Direct default-branch commits are preferred over PRs. No force-push, no moving a published tag, and no replacing a release asset with different bytes.
- **D2 — Keep the current sources.** FFmpeg n9.0.2, dav1d 1.5.4, and zlib 1.3.2 stay pinned. An upstream FFmpeg upgrade is a separate change after extraction parity.
- **D3 — First producer release is a normal release**, not a prerelease. Consumers enumerate `releases.atom`, never `/releases/latest`.
- **D4 — Product changes.** `usr` installs the tools group by default on the three supported targets; `encode` gains an early failure on non-macOS; Player gets patch release `v0.42.1`.

### Prescribed

- **P1 — Names.** Artifacts are `ffmpeg-<upstream>+<tag>-<target>-play-sdk.tar.gz` and `ffmpeg-<upstream>+<tag>-<target>-tools.tar.gz`, with targets `aarch64-apple-darwin`, `x86_64-unknown-linux-musl`, `aarch64-unknown-linux-musl`. Release tag is `YYYYMMDD` for the first release of a UTC day and `YYYYMMDD-rN` for later revisions. The `+` separates upstream version from release identity. Reverse only before the first publication.
- **P2 — Layout.** SDK: `include/`, `lib/*.a`, `lib/pkgconfig/*.pc`, `share/ffmpeg-build/manifest.json`, `share/licenses/`, `README`. Tools: `bin/ffmpeg`, `bin/ffprobe`, `share/ffmpeg-build/manifest.json`, `share/licenses/`, `README`. `usr` never installs development headers or libraries.
- **P3 — Dependency closure.** Ship static `libdav1d.a` and `libz.a` in both SDKs; tools link them statically. This replaces Player's shared macOS dav1d and its SDK-zlib `zlib.pc`, removes the duplicate zlib recipe, and makes the SDK self-contained. Reverse if a static zlib conflicts with a consumer; none does today.
- **P4 — Platform flags.** `play-sdk`: VideoToolbox on macOS; `--enable-pic --enable-vaapi` on Linux. Declare `VideoToolbox`, `CoreFoundation`, `CoreMedia`, `CoreVideo`, `CoreServices` on macOS and `libva`/`libva-drm` on Linux. No GPU drivers or desktop stacks in the SDK. `tools` is headless: no VA-API, no VideoToolbox decode, no devices; macOS keeps `--enable-videotoolbox --enable-audiotoolbox` for the `encode` encoders.
- **P5 — Player pin.** `play/ffmpeg-sdk.lock.json` carries `contract: 1`, the producer release tag, `profile: play-sdk`, the FFmpeg source version, and a target-to-`{asset, sha256}` map. `scripts/fetch-ffmpeg-sdk.sh` verifies the SHA before extraction and rejects an archive whose manifest disagrees with the pin. `FFMPEG_PREFIX` overrides must pass the same check.
- **P6 — Player discovery.** `rust/player-media/build.rs` uses `pkg-config --static` against the SDK prefix only, with a backslash-aware tokenizer for paths containing spaces. It emits `rerun-if-changed` for the manifest, `include/`, and `lib/`, and has no fallback to a system, Homebrew, or old local prefix. On Linux, resolve `libva`'s libdir with pkg-config and pass `libva.so`/`libva-drm.so` by absolute name; this keeps the existing musl-linker workaround but removes the hardcoded `/usr/lib` path.
- **P7 — Audit split.** The producer validates the complete resolved configuration against its profile. Player's `scripts/ffmpeg-manifest.sh` keeps its name and gate but reads the shipped manifest and checks the profile contract: `play-sdk`, the Rust target, FFmpeg 9.0.2, no encoders/muxers/devices/network, `file` as the only protocol, `dav1d` as the only external library, `dav1d`/`zlib` as the only bundled dependencies, and the required playback decoders/demuxers present. It does not duplicate the full allowlist. `tests/harness.py` updates its required-path list to the pin and fetch script.
- **P8 — Fixtures are test-only.** `tests/fixtures/gen.sh` keeps using a full host FFmpeg 9.0.2 (Homebrew on macOS, Alpine `ffmpeg` in the container). The shipped `tools` profile is not expanded to satisfy fixture generation. Document the dependency.
- **P9 — `usr` layout.** Install to `$XDG_DATA_HOME/ffmpeg/releases/<tag>-<triple>/`, point `$XDG_DATA_HOME/ffmpeg/current` at it, and make `${DEST}/ffmpeg` and `${DEST}/ffprobe` symlinks through `current`. State record `${STATE}/ffmpeg` is `<tag>:<etag>`. Discover the newest tag from `releases.atom`; verify `SHA256SUMS`; stage, smoke-test both commands, then promote. Keep the previous pair on any failure.
- **P10 — `usr` health.** Add `ffmpeg` to `dl --list` defaults for Darwin:aarch64, Linux:x86_64, and Linux:aarch64. `dl ffmpeg` installs or repairs both commands. `host/alpine/install.sh`, `host/alpine/verify.sh`, and `dotfiles/doctor` treat `ffmpeg` as a pair and check both launchers.
- **P11 — `encode`.** Add an early non-Darwin failure with a clear message. Keep the macOS command unchanged. No Linux HEVC encoder or x265 dependency.
- **P12 — CI.** macOS on `xcode-27`; Linux on `ubuntu-latest` and `ubuntu-24.04-arm`, natively, inside digest-pinned Alpine. Pin every action to a full commit SHA. Only the publish job gets `contents: write`. CI invokes the same local commands as the executor.
- **P13 — Producer controller.** Python 3 standard library `build.py` with `fetch`, `build`, `audit`, `package`, and `qualify` subcommands; `sources.lock.json`; `profiles/<profile>.json`. Python is present on every build host and avoids a new runtime dependency. Generated JSON manifests are fine; no hand-maintained component metadata.
- **P14 — Archives.** Build deterministic `tar.gz` with Python `tarfile` (sorted entries, uid/gid 0, mtime 0, gzip mtime 0). Publish `SHA256SUMS` and a `release.json` with tag, commit, and asset digests. Ad-hoc sign macOS tools before packaging. Preserve symbols in SDK archives; strip only runtime executables.
- **P15 — Player release.** Bump `player-app` to `0.42.1`, tag `v0.42.1`, and keep `usr`'s existing `PLAYER_REPO=joshuarli/play`.
- **P16 — Player budget.** Keep the existing 29,542,136 B distributable budget. If the SDK migration exceeds it, park and report; do not raise it silently.

### Delegated

- **Tools component set.** The executor chooses the exact decoders, encoders, muxers, parsers, bitstream filters, filters, and protocols from the workflows in S3, within these bounds: every component is justified by a named fixture or command; no external library beyond dav1d and zlib; no network protocol, device, `ffplay`, or program beyond `ffmpeg`/`ffprobe`; no encoder that is not needed by a documented workflow. Record requested versus auto-selected components in the manifest and `docs/tools-profile.md`.
- **Exact configure flags** inside P4/P13 (for example `--enable-small` or `--extra-cflags`), provided the audit proves the profile restrictions and the CPU baseline stays portable.
- **Exact cache keys and job names** inside P12, provided every key includes the source lock, profile, scripts, target, and toolchain identity.
- **Exact `dl` function structure** inside P9/P10, provided the layout, ownership, repair, and preservation rules hold.

## Baseline

Verified at preflight on 2026-11-04:

| Repository | Baseline in draft | Current HEAD | Relevant drift |
| --- | --- | --- | --- |
| `~/d/play` | `da0c70dbde2b` | `3bf9b42d4143` | one `docs/metrics.md` line; no code change |
| `~/usr` | `33b5e483bd7b` | `864a2e55ded1` | `agent-memory` worker changes only |
| `~/d/python-build` | `f1a5f743eb23` | `f1a5f743eb23` | none |

`~/d/ffmpeg-build` has no commits, only this draft; its remote is `laputa-systems/ffmpeg-build` and it is public. The `usr` checkout is one commit ahead of origin; preserve it.

Recorded Player baseline at `da0c70dbde2b` (`docs/metrics.md`, `docs/ffmpeg.md`): macOS release 7,107,568 B, stripped; closure 12,606,880 B; 8 files; one `file` protocol; corpus 104/0, audio 15/0, hwdec 8/0, seek 5/0, FFmpeg audit 19/0. Linux release 23,820,624 B, 7 `NEEDED` entries. These are the comparison numbers; re-run the narrow gates at S0 if a local artifact is missing.

Known red or deferred, not migration regressions: PLAY-20 (hardware decode not wired), PLAY-21 (terminal focus), PLAY-23/24 (HE-AAC and unusual AAC layouts), PLAY-25 (GUI cover art), PLAY-26/27/28 (subtitle styling and line layout), PLAY-29 (GUI CPU re-measure). `scripts/audit.sh` needs a built `build/mpv`; a missing build is not a red test.

Loop timings measured today on this host (busy with unrelated work; `perf-gate-ready` reported a hot process tree): macOS `play-sdk` build 74 s, macOS `tools` build 64 s, Linux x86-64 `tools` build 157 s under Docker emulation, relocated SDK link under 5 s. Native CI should be faster. Treat Player `measure.sh final` as deferred while the host is busy and record `perf gate deferred: host busy`.

## Sequence

Each item ends on its acceptance command and the narrowest affected suite. Full Player suite runs at S8 and S12. Red work stays on its branch.

### S0 — Baseline and producer skeleton

**Owns.** `ffmpeg-build/{AGENTS.md,README.md,.gitignore,sources.lock.json,profiles/play-sdk.json,profiles/tools.json,docs/baseline.md}`; `.git/info/exclude`.

**Prereq.** None.

**Acceptance.**
```sh
cd /Users/josh/d/ffmpeg-build
git check-ignore -q .work
jaq -e . sources.lock.json profiles/play-sdk.json profiles/tools.json
git status --short
```
Pass: `.work/` is ignored, all JSON parses, and only intended files are staged. Fail: `.work/` is tracked, a source pin lacks a SHA, or a profile lacks its target scope.

Write the three source pins with URL and SHA-256, the initial profile files, a short `AGENTS.md` (commands, invariants, no `/tmp`), and `README.md` (what the repo owns, how to build one target/profile). `docs/baseline.md` records the commands and results re-run from this checkout; it is evidence, not a history log. Do not add generated metadata by hand.

### S1 — Shared build core and macOS `play-sdk`

**Owns.** `build.py`, `tests/`, `profiles/play-sdk.json`, `docs/play-sdk.md`.

**Prereq.** S0.

**Acceptance.**
```sh
python3 build.py fetch --target aarch64-apple-darwin --profile play-sdk
python3 build.py build --target aarch64-apple-darwin --profile play-sdk
python3 build.py audit --target aarch64-apple-darwin --profile play-sdk
```
Pass: hashes verify on cached and fresh downloads; the build writes static archives and headers; `ffversion.h` says `9.0.2`; the audit finds no programs, encoders, muxers, devices, or network protocols; the resolved decoders/demuxers/parsers/bsfs/filters/hwaccels contain every requested component; auto-selected components (`h263`, `vp9_superframe_split`, and anything else) are recorded; `.pc` files contain no absolute build prefix; archives are PIC and contain ordinary machine code, not LTO bitcode; the manifest records `cc --version`, the SDK/sysroot, the CPU baseline, and the effective configure arguments. Fail: a requested component is absent (this is how `mov_text` silently failed in the proof; the configure component is `movtext`), a network/encoder/muxer/device appears, an archive is LTO-only, or the version is not upstream 9.0.2.

Start `play-sdk` from the verified allowlist at `play/scripts/ffmpeg-components.txt:1-9`: all current demuxers, video/image decoders, parsers, filters, bitstream filters, platform hwaccels, and the `file` protocol. Keep the PNG/JPEG album-art paths and the macOS VideoToolbox / Linux VA-API split. The producer's profile is the new authoritative copy; the current allowlist is the parity baseline.

Build from `sources.lock.json` only. Write `VERSION` into the extracted FFmpeg tree before configure. Separate `.work/build/<target>/<profile>` and `.work/stage/<target>/<profile>`. Include the source lock, profile, scripts, target, profile, flags, and toolchain in the build stamp.

### S2 — Linux `play-sdk` for both targets

**Owns.** `profiles/play-sdk.json` Linux flags, `scripts/linux-build.sh`, `docker/` or the container invocation, `docs/play-sdk.md`.

**Prereq.** S1.

**Acceptance.**
```sh
scripts/linux-build.sh x86_64-unknown-linux-musl play-sdk
scripts/linux-build.sh aarch64-unknown-linux-musl play-sdk
```
Pass: each audit reports the right ELF architecture, the compiler and sysroot, and the symbol-version/ABI notes; `--enable-pic` is present; no `-march=native` or host-specific CPU flag; no glibc artifact; `.pc` files declare `libva`/`libva-drm`; the archive contains no programs. Fail: an x86-64 flag leaks into aarch64, the interpreter or a GNU dependency appears, a symbol version exceeds the stated baseline, or the build needs a `play` checkout.

Run the x86-64 build under `linux/amd64` and the arm64 build under `linux/arm64`; on this Apple Silicon host the arm64 build is native. CI uses native runners.

### S3 — macOS `tools` profile and fixture workflows

**Owns.** `profiles/tools.json`, `tests/fixtures/gen.sh`, `tests/tools-workflows.sh`, `tests/encode-command.sh`, `docs/tools-profile.md`.

**Prereq.** S1.

**Acceptance.**
```sh
python3 build.py build --target aarch64-apple-darwin --profile tools
python3 build.py audit --target aarch64-apple-darwin --profile tools
tests/tools-workflows.sh .work/stage/aarch64-apple-darwin/tools
tests/encode-command.sh .work/stage/aarch64-apple-darwin/tools
```
Pass: `ffmpeg` and `ffprobe` report 9.0.2; `ffplay` is absent; `-buildconf` has `--disable-network`; `otool -L` lists only system libraries/frameworks and no `/opt/homebrew`; probe JSON works; video+audio merge and remux work; SRT converts to `mov_text`; PNG/JPEG thumbnails embed with metadata; the `encode` command produces HEVC `hvc1` + AAC + `mov_text` with `+faststart`. Fail: a workflow needs an external library beyond dav1d/zlib, a network/device feature is enabled, a Homebrew library is linked, or the `encode` command cannot select its encoders.

The tools profile owns its audio decoders and encoders; Player's Rust audio does not supply them. Keep `--disable-autodetect` and explicit feature selection; enable only `file`, `pipe`, and `fd` protocols. Every external library beyond dav1d and zlib needs a named workflow. Exclude `ffplay`, devices, and desktop/audio-output stacks; the Linux pair must run headless on Alpine. yt-dlp remains the downloader; FFmpeg is not a network client. Determine the component set by running the actual postprocessing commands on representative fixtures, not by guessing.

Use fixtures generated by a full host FFmpeg 9.0.2. Every added component must be named by a failing workflow. `encode` hardware execution is reported separately; encoder availability is not proof of hardware execution.

### S4 — Linux `tools` for both targets

**Owns.** `profiles/tools.json` Linux flags, `scripts/linux-build.sh`, `tests/tools-workflows.sh`, `docs/tools-profile.md`.

**Prereq.** S3.

**Acceptance.**
```sh
scripts/linux-build.sh x86_64-unknown-linux-musl tools
scripts/linux-build.sh aarch64-unknown-linux-musl tools
```
Pass: `file` reports static-pie (or static) ELF for the right architecture; no `INTERP` or `NEEDED`; no glibc string; both commands run in a clean Alpine container with no build prefix; the same probe/merge/remux/subtitle/thumbnail workflows pass; `hevc_videotoolbox` and `aac_at` are absent. Fail: a dynamic musl/glibc dependency appears, the binary needs `/work`, or a workflow fails on a clean Alpine.

### S5 — Manifest, packaging, relocation, and qualification

**Owns.** `build.py` package/qualify, `tests/sdk-consumer.c`, `tests/qualify-sdk.sh`, `tests/qualify-tools.sh`, `docs/artifacts.md`.

**Prereq.** S1-S4.

**Acceptance.**
```sh
python3 build.py package --target aarch64-apple-darwin --profile play-sdk --tag local
python3 build.py package --target aarch64-apple-darwin --profile tools --tag local
python3 build.py qualify --archive dist/ffmpeg-9.0.2+local-aarch64-apple-darwin-play-sdk.tar.gz
python3 build.py qualify --archive dist/ffmpeg-9.0.2+local-aarch64-apple-darwin-tools.tar.gz
```
Pass: the archive root is the expected name; the manifest has `contract`, `profile`, `target`, `sources`, `producer`, `configure_args`, `components`, `auto_selected`, `external_libraries`, `bundled_dependencies`, `frameworks`, and `toolchain`; the archive carries upstream licenses/notices; every `.pc` uses `${pcfiledir}` and no build prefix remains; extraction into a path with spaces, `pkg-config --static`, and a real external link work; the consumer runs and links only system libraries; the tools archive runs both commands and the workflows without the build prefix. Fail: an absolute build path survives, `pkg-config` cannot find the SDK, the consumer needs Homebrew or `/work`, a notice is missing, or the manifest disagrees with the archive name.

The SDK consumer must use `eval` or a Makefile to honor pkg-config's backslash-escaped spaces; direct unquoted `$(pkg-config ...)` splits the path and is not a valid test.

### S6 — Release CI and first producer release

**Owns.** `.github/workflows/release.yml`, `.github/scripts/resolve_release.py`, `docs/release.md`, `sources.lock.json`.

**Prereq.** S5.

**Acceptance.**
```sh
jaq --from yaml . .github/workflows/release.yml >/dev/null
python3 -m unittest discover -s tests
git push origin main
gh workflow run release.yml -f release_tag=20261104
gh run watch
gh release view 20261104 --json tagName,isPrerelease,assets
gh release download 20261104 --pattern SHA256SUMS --dir .work/tmp/release-check
(cd .work/tmp/release-check && sha256sum -c SHA256SUMS)
```
Pass: the tag resolves from the input or the UTC date; an existing tag at a different commit is rejected; six archives, `SHA256SUMS`, and `release.json` are present; `isPrerelease` is false; every archive is extracted and qualified from its published bytes; `SHA256SUMS` verifies. Fail: a job uses a floating action/image, the publish job runs before qualification, an asset is overwritten, or the release references a commit other than `GITHUB_SHA`.

Jobs: `prepare`, `build-macos`, `build-linux` (x86-64 and arm64), `assemble`, `qualify-macos`, `qualify-linux` (both arches), `publish`. Pin `actions/checkout`, `actions/cache`, `actions/upload-artifact`, `actions/download-artifact`, and the Alpine images to the same full SHAs/digests already used by `play` and `python-build`; verify the digests before use. The publish job alone gets `contents: write`. Never overwrite an existing release; rerun with `YYYYMMDD-r2`.

### S7 — Player pin, fetch, and build

**Owns.** `play/ffmpeg-sdk.lock.json`, `play/scripts/fetch-ffmpeg-sdk.sh`, `play/rust/player-media/build.rs`, `play/scripts/build-deps.sh`, `play/scripts/build-deps-linux.sh`, `play/scripts/build.sh`, `play/scripts/release.sh`, `play/.github/workflows/{macos,linux}.yml`; delete `play/scripts/build-ffmpeg.sh` and `play/scripts/ffmpeg-components.txt`.

**Prereq.** S6.

**Acceptance.**
```sh
cd /Users/josh/d/play
scripts/fetch-ffmpeg-sdk.sh aarch64-apple-darwin
cargo build --manifest-path rust/Cargo.toml -p player-app
tests/run.sh ffmpeg-audit
tests/run.sh build
```
Pass: the pin contains the published tag and real SHA-256; fetch verifies before extraction; the extracted prefix is target-specific; `build.rs` finds only that prefix; a missing or wrong-profile SDK fails with a clear message; `FFMPEG_PREFIX` is validated; no `build-ffmpeg.sh` or `ffmpeg-components.txt` remains in scripts; the old FFmpeg source build is gone; `MACOSX_DEPLOYMENT_TARGET=27.0` and Player's macOS arm64 plus Linux x86-64 musl platform contract are unchanged. Fail: a system/Homebrew FFmpeg can satisfy the build, the pin references an unpublished tag or imaginary checksum, the build still searches `.work/deps/ffmpeg-full` or `.work/deps/release/ffmpeg`, or a new Player platform appears.

For Linux, run `scripts/linux-container.sh scripts/fetch-ffmpeg-sdk.sh x86_64-unknown-linux-musl`, then `scripts/linux-container.sh scripts/build-linux.sh` and `scripts/linux-container.sh scripts/audit-linux.sh`. Update both CI caches and dependency stamps to include `ffmpeg-sdk.lock.json` and the fetched SDK path. Search `rg -n 'ffmpeg|FFMPEG|dav1d|zlib' play` and update every hit, including development, release, Linux-container, and audit scripts, `build.rs`, native bindings/ABI checks, CI caches/stamps, packaging, fixtures, and docs.

### S8 — Player audits, docs, and measurement

**Owns.** `play/scripts/ffmpeg-manifest.sh`, `play/tests/harness.py`, `play/tests/fixtures/gen.sh` (test-only note), `play/docs/{ffmpeg,architecture,install,linux,metrics}.md`.

**Prereq.** S7.

**Acceptance.**
```sh
cd /Users/josh/d/play
tests/run.sh ffmpeg-audit
scripts/audit.sh
cargo test --manifest-path rust/Cargo.toml
tests/run.sh suite
scripts/measure.sh final
```
Pass: the audit reads the SDK manifest and checks the profile contract; `scripts/audit.sh` passes its four gates; Rust tests and the full suite pass; `measure.sh final` passes or exits 75 with `perf gate deferred: host busy`; the metrics row records the new size and dependency set; the budget still holds; the app runs from `dist/Player.app` without `usr`, a global FFmpeg, or a sibling checkout; Linux keeps the documented musl/Wayland/Vulkan/ALSA/libva `NEEDED` set. Fail: the audit reads a build tree, a source-layout assertion still names the removed scripts, the runtime gains a global FFmpeg dependency, or the distributable exceeds 29,542,136 B.

Keep the no-network, no-unwanted-codec/program, required-playback, and dependency-closure checks. Update `tests/harness.py` required paths to `ffmpeg-sdk.lock.json` and `scripts/fetch-ffmpeg-sdk.sh`, and drop `build-ffmpeg.sh`/`ffmpeg-components.txt`. Document the test-only host FFmpeg for fixtures. Explain material size/dependency differences against the baseline. The suite covers corpus, audio, seek, album-art, local-input, and release/dependency gates. Run the Linux half in the container: `scripts/linux-container.sh tests/run.sh suite`; it is the milestone proof for the musl runtime set.

### S9 — `usr` installer, defaults, and tests

**Owns.** `usr/dl`, `usr/dotfiles/dl-test.sh`, `usr/dotfiles/doctor`, `usr/dotfiles/doctor-test.sh`, `usr/host/alpine/install.sh`, `usr/host/alpine/verify.sh`, `usr/docs/`.

**Prereq.** S6.

**Acceptance.**
```sh
cd /Users/josh/usr
sh dotfiles/dl-test.sh
sh dotfiles/doctor-test.sh
shellcheck -s sh dl dotfiles/dl-test.sh dotfiles/doctor dotfiles/doctor-test.sh host/alpine/install.sh host/alpine/verify.sh
sh -n dl host/alpine/install.sh host/alpine/verify.sh
dash -n dl dotfiles/doctor
```
Pass: all new cases pass. Fail: any target mapping is wrong, a GNU fallback is reachable, a checksum/extraction failure replaces a working install, or an unmanaged file is removed.

Recheck the `usr` HEAD and confirm there is still no FFmpeg installer or Brewfile/Alpine package entry before editing those files. Add cases for: the three target mappings and unsupported-target rejection; install of both commands from one release; repeat install; upgrade; missing-`ffprobe` repair; checksum mismatch and extraction failure preserving the previous pair; managed ownership and unmanaged-file preservation; default-tool selection and pair completeness; prerelease discovery through `releases.atom`; missing-asset handling; `dl --list`; `sync tools ffmpeg`; `doctor` checking both. Use the existing mock `curl`/`uname`/`tar` harness and scratch `HOME` roots. Record both launchers, the versioned directory, and `current` in the ownership file.

### S10 — `usr` end-to-end install and verification

**Owns.** `usr/docs/`, scratch install under `usr/.work/`.

**Prereq.** S9 and S6.

**Acceptance.**
```sh
cd /Users/josh/usr
home=$PWD/.work/tmp/ffmpeg-home
mkdir -p "$home"
HOME="$home" sh dl ffmpeg
"$home/.local/bin/ffmpeg" -version
"$home/.local/bin/ffprobe" -version
HOME="$home" sh dl ffmpeg
rm "$home/.local/bin/ffprobe"
HOME="$home" sh dl ffmpeg
test -x "$home/.local/bin/ffprobe"
HOME="$home" sh dl --list | grep -qx ffmpeg
```
Pass: both commands install from the published release; repeat is current; the missing sibling is repaired; `dl --list` includes `ffmpeg` on supported targets; `doctor` reports both. Fail: the installer touches the working host, a disposable fixture is not used, or the pair is promoted without smoke-testing both commands.

Exercise probe, merge/remux, metadata, subtitle-to-SRT, and thumbnail embedding with disposable local fixtures. Run a local yt-dlp postprocessing path with `PATH` pointing at the managed pair (no network download), or the equivalent merge/thumbnail/subtitle commands, and confirm `encode` resolves the managed `ffmpeg`. Test `encode` on Apple hardware in a disposable directory; `encode` trashes originals when the output is smaller. Report hardware-dependent checks that could not run. Do not run `sh sync`, host setup, or reset scripts against the working host.

### S11 — Player patch release

**Owns.** `play/rust/player-app/Cargo.toml`, tag `v0.42.1`.

**Prereq.** S8.

**Acceptance.**
```sh
cd /Users/josh/d/play
# bump player-app to 0.42.1 and commit
git tag v0.42.1
git push origin main v0.42.1
gh run watch
gh release view v0.42.1 --json tagName,assets
```
Pass: both release jobs build from the pinned SDK; the macOS bundle has no Homebrew path; the Linux audit passes; `SHA256SUMS` verifies. Fail: the release uses a source FFmpeg build, a job needs the old prefix, or the tag is moved after publication. Use `v0.42.2` for a retry.

### S12 — Rollout, report, and close

**Owns.** `ffmpeg-build/docs/release.md`, final report.

**Prereq.** S10 and S11.

**Acceptance.**
```sh
gh release download 20261104 --pattern SHA256SUMS --dir .work/tmp/producer-release
(cd .work/tmp/producer-release && sha256sum -c SHA256SUMS)
gh release view v0.42.1 --json tagName,assets
(cd /Users/josh/d/play && tests/run.sh suite)
cd /Users/josh/usr
home=$PWD/.work/tmp/rollout-home
mkdir -p "$home"
HOME="$home" PLAYER_APPLICATIONS_DIR="$home/Applications" sh dl player
HOME="$home" sh dl ffmpeg
```
Pass: the producer release, Player release, and `usr` install all verify from published bytes; `docs/release.md` has the target/profile matrix, artifact sizes, dependency sets, exact consumer build/install commands, supported CLI workflows, intentional limitations, and the FFmpeg update procedure; the final reply has the three commit IDs, release tags/URLs, matrix, sizes/dependencies, exact commands, workflows/limitations, verification results, and environment gaps. Fail: a consumer references an unpublished tag, a checksum is unverified, or the report claims a hardware/environment check that did not run.

Run the `review` skill on the final diff and fix P1/P2 findings before closing. Remove campaign worktrees and scratch; leave only retained trees with a reason.

## Acceptance matrix

| Deliverable | Proof | Pass | Fail |
| --- | --- | --- | --- |
| Producer builds one target/profile | `python3 build.py build/audit ...` | requested components present, restrictions hold, hashes verified | missing component, network/encoder/muxer/device, wrong version |
| Six archives | `build.py package`, CI assemble | six named archives + `SHA256SUMS` + `release.json` | missing asset, wrong name, non-deterministic bytes |
| Relocatable SDK | `build.py qualify` in a path with spaces | `pkg-config --static`, external link, consumer runs, system-only linkage | build prefix or Homebrew needed |
| Static musl tools | clean Alpine run | static-pie, no `INTERP`/`NEEDED`, workflows pass | glibc, dynamic dependency, missing workflow |
| Player consumes pin | fetch + build + audit | SDK-only discovery, manifest contract, no old recipe | system FFmpeg satisfies build, stale pin |
| Player release | `v0.42.1` workflow | both artifacts, no Homebrew, Linux audit | old source build, moved tag |
| `usr` pair | `dl-test.sh` + scratch install | both commands, repair, preservation, defaults | partial pair, GNU fallback, lost install |
| Rollout | release download + install | published bytes verify end to end | unpublished tag or unverified checksum |

## Needs environment

- **Apple hardware VideoToolbox execution.** Run `encode archive-720p-cq52 <disposable fixture>` on Apple Silicon and confirm an `hvc1` HEVC + AAC output. The executor may have this host; if not, report encoder availability only.
- **Real Alpine host provisioning.** Run `doas env INSTALL_MODE=server sh usr/host/alpine/install.sh` and then `doas sh usr/host/alpine/verify.sh` on a disposable Alpine edge host. The container tests do not prove host provisioning.
- **Real GPU VA-API decode.** `tests/run.sh linux-vaapi` with a `/dev/dri/renderD*` node and a VA driver. The SDK's VA-API linkage is audited locally; hardware decode is an owner check and is not required for this campaign.
- **Player GUI, audio, and visual checks.** `scripts/manual-checklist.sh --fixture-dir .work/fixtures --release` on the owner's machine.
- **GitHub runners.** `xcode-27`, `ubuntu-latest`, and `ubuntu-24.04-arm` must be available for publication. If one is unavailable, finish local implementation, park the release, and report the exact missing runner.

## Execution boundary and non-goals

**Authorized.** Edit and push the three named repositories; create tags and releases; run GitHub Actions; download pinned sources; build in Docker; install into scratch `HOME` roots; ad-hoc sign macOS binaries; use `.work/` for all scratch.

**Forbidden.** Push any other repository or tag; force-push; overwrite a release asset; change Player's playback architecture, Rust audio ownership, subtitles, local-only behavior, or application behavior; add a Linux HEVC encoder or x265; port Player to ARM64 Linux; add network protocols to either FFmpeg profile; produce a glibc artifact or fallback; use `/tmp` or `$TMPDIR`; run host setup, `sh sync`, or reset scripts against the working host; modify user data outside `.work/`; raise the Player budget.

**Contract changes to surface.** Producer artifact names and manifest schema; the Player pin file and `FFMPEG_PREFIX` validation; the `encode` non-macOS failure; the `usr` default tool set and install layout; Player `v0.42.1`. Update code, tests, and docs together.

**Non-goals.** FFmpeg upgrade; Player ARM64 Linux; Linux `encode`; GUI/visual changes; FFmpeg as a network downloader; Homebrew runtime dependencies; notarization; changing the existing Player installer's supported platforms.

## Reference

**Producer inputs.**
- FFmpeg n9.0.2 tarball `https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n9.0.2.tar.gz`, SHA-256 `6e374ed621e48faa40639307dff48ba6fe574a509977956d2cce9669b7cc27e9` (`play/scripts/build-ffmpeg.sh:5-8`).
- dav1d 1.5.4 tarball SHA-256 `2abfb0c89212e6e4733a54e0ae509ec00a5b845a6360946f918806e14aedb011` (`play/scripts/build-deps.sh:127-137`).
- zlib 1.3.2 tarball SHA-256 `d7a0654783a4da529d1bb793b7ad9c3318020af77667bcae35f95d0e42a792f3` (`play/scripts/build-deps-linux.sh:105-112`).

**Current Player recipe and checks.**
- `play/scripts/build-ffmpeg.sh:60-72` configure; `:74-105` allowlist parser; `:113-120` Linux install and `.pc` rewrite.
- `play/scripts/ffmpeg-components.txt:1-9` playback allowlist.
- `play/scripts/ffmpeg-manifest.sh:18-32` build-tree paths and auto-selected sets; `:134-208` restrictions.
- `play/rust/player-media/build.rs:5-22` fixed prefixes; `:40-102` link logic and platform split.
- `play/tests/harness.py:1688-1750` `gate_meta` required paths.
- `play/docs/ffmpeg.md:1-60` current pin/build/audit; `play/docs/metrics.md` baseline rows.

**`usr` installer patterns.**
- `usr/dl:120-145` ownership; `:466-478` `asset_id`/`is_current`; `:585-680` generic release install and GNU fallback; `:1564-1740` Player grouped install; `:2735-3010` Git versioned/current install; `:3472-3620` ownership reconciliation; `:3640-3735` defaults and dispatch.
- `usr/dotfiles/dl-test.sh:1402-1410` default-target case; `:2517-2700` Player install/repair/preservation cases.
- `usr/host/alpine/install.sh:207-218` default-tool provisioning; `usr/host/alpine/verify.sh:46-52` default-tool check and `:100-101` Player checks; `usr/dotfiles/doctor:55-69` default-tool check.
- `usr/dotfiles/base/.local/bin/encode:34-75` exact `ffmpeg` command. `usr/dotfiles/base/.local/bin/{vdl,mdl,mpdl,yt-dlp}` drive yt-dlp postprocessing (`--convert-subs srt`, `--embed-thumbnail`, `--embed-metadata`, `--merge-output-format mp4`); S10 verifies they resolve the managed pair, with no code change expected.

**`python-build` conventions.**
- `.github/scripts/resolve_release.py:10-31` tag resolution; `.github/workflows/build.yml:42-47` prepare; `:493-526` prerelease publish; `Dockerfile:1-2` pinned Alpine digests.

**Artifact and manifest contract.** The SDK manifest is generated from `config_components.h` and `config.mak`; it records requested and auto-selected components, configure arguments, sources, producer commit, target, profile, toolchain, external libraries, and frameworks. The tools manifest records the same minus consumer linkage. `SHA256SUMS` and `release.json` are the only hand-independent release metadata.

**Update procedure.** To move FFmpeg: change `sources.lock.json`, run the full local matrix and audits, publish a new date/build-revision release, update `play/ffmpeg-sdk.lock.json` with the new tag and real SHAs, rebuild/qualify Player, publish a Player patch release, and let `usr` discover the new tools release. Never point a consumer at a tag before its release and checksums exist.
