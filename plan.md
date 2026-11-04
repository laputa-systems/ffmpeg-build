# Extract FFmpeg into `laputa-systems/ffmpeg-build` and integrate `play` and `usr`

Implement this migration end to end across:

- **Producer:** this repo
- **Playback consumer:** ~/d/play
- **CLI installation consumer:** ~/usr
- **Reference for build/release conventions:** ~/d/python-build

Make `ffmpeg-build` the authoritative home for the custom FFmpeg sources, pins, configuration, codec dependency recipes, packaging, audits, and releases. Update `play` to consume a pinned SDK release, and update `usr` to install the released `ffmpeg` and `ffprobe` commands.

Work through implementation, verification, initial publication, and consumer integration. Make coherent commits in each changed repository and use their existing release workflows. Prefer direct default-branch commits over PR ceremony. Preserve unrelated work. Treat `python-build` as a reference repository.

## 1. Platform and scope requirements

Produce both the playback SDK and CLI tools for:

| Target | Platform |
|---|---|
| `aarch64-apple-darwin` | Apple Silicon macOS |
| `x86_64-unknown-linux-musl` | x86-64 Linux, tested on Alpine |
| `aarch64-unknown-linux-musl` | ARM64 Linux, tested on Alpine |

**All Linux artifacts and their target dependencies must use musl.** There must be no GNU/glibc artifact, glibc fallback, or dependency on a glibc compatibility layer.

macOS uses its native Apple SDK, libSystem, and explicitly required Apple frameworks. The musl requirement applies to Linux.

Build Linux artifacts inside pinned Alpine environments for the correct architecture. An Ubuntu GitHub runner may orchestrate the containers; target compilation, dependency discovery, linking, and Linux runtime qualification belong in the musl environment.

Use native architecture CI where available. Record the compiler/sysroot and inspect final ELF architecture, interpreter, dependencies, and symbol versions. Keep CPU requirements explicit and portable; do not publish binaries built with an accidental host-specific `-march=native`.

Preserve the existing macOS deployment floor and Player platform contract. At the inspected baseline, Player supports macOS arm64 and Linux x86-64 musl. Publishing an ARM64 Linux FFmpeg SDK does not make porting Player to ARM64 part of this campaign.

Keep this focused on extracting and distributing FFmpeg. Preserve Player’s current playback architecture, local-only behavior, Rust audio ownership, subtitles, and application behavior.

## 2. Inspect the live repositories and establish the baseline

Read each repository’s instructions and current HEAD before editing. The research baseline was:

- `play`: `da0c70dbde2b254ad5499109900681ba06cb1cb4`
- `usr`: `33b5e483bd7b18f462b5144a9576de1400b6ed6a`
- `python-build`: `f1a5f743eb23414fed6ea8a4dcc873bfb7c73822`

Account for any newer changes.

In `play`, trace every FFmpeg reference, including:

- `scripts/build-ffmpeg.sh`
- `scripts/ffmpeg-components.txt`
- `scripts/ffmpeg-manifest.sh`
- `scripts/build-deps.sh`
- `scripts/build-deps-linux.sh`
- Development, release, Linux-container, and audit scripts.
- `rust/player-media/build.rs`, native bindings, and relevant ABI checks.
- CI cache keys, dependency stamps, release packaging, fixtures, and documentation.

At the baseline, FFmpeg is pinned to **n9.0.2**, dav1d to **1.5.4**, and zlib to **1.3.2**. Carry forward the verified source identities and hashes from the actual recipes. Establish extraction parity before considering an upstream upgrade.

Record the existing effective configuration, dependency linkage, relevant artifact sizes, and applicable test results. Distinguish existing failures from migration regressions.

In `usr`, inspect `dl`, its installer tests, ownership tracking, default tools, doctor, Alpine installation/verification, and these scripts:

- `dotfiles/base/.local/bin/encode`
- `dotfiles/base/.local/bin/vdl`
- `dotfiles/base/.local/bin/mdl`
- `dotfiles/base/.local/bin/mpdl`
- `dotfiles/base/.local/bin/yt-dlp`

In `python-build`, adopt the useful production conventions: locked inputs, explicit targets, relocatable archives, checksums, source identity, and qualification of the exact packaged bytes. Keep the new implementation compact; the Python-specific runtime and research machinery is unnecessary here.

## 3. Build two explicit profiles with shared infrastructure

Use one authoritative source/dependency lock and shared fetch/build/package infrastructure, with two small explicit configurations.

### Profile A: `play-sdk`

Preserve the current minimal playback configuration.

Requirements:

- Static FFmpeg libraries and public headers.
- Relocatable pkg-config metadata.
- The actual codec dependency closure and its link metadata.
- A generated manifest identifying the target, profile, source versions, producer commit, effective configuration, and resolved components.
- Existing demuxers, video/image decoders, parsers, filters, bitstream filters, and supported platform acceleration components.
- The existing absence of FFmpeg audio decoders, encoders, muxers, devices, network protocols, and CLI programs.
- Player’s file-only protocol contract.

Preserve the PNG/JPEG album-art paths and the existing platform distinctions: VideoToolbox on macOS and the supported VA-API configuration on Linux. Correct the current x86-64-specific build assumptions when producing an ARM64 SDK.

Retain the distinction between requested components and components FFmpeg automatically selects. The current build accounts for dependencies such as `h263` and `vp9_superframe_split`; audit the complete resolved configuration.

### Profile B: `tools`

Produce a practical, narrowly configured `ffmpeg` and `ffprobe` pair for `usr`.

This profile needs its own explicit decoder/encoder/muxer requirements. Player’s Rust audio implementation does not supply audio decoding to standalone FFmpeg commands.

Audit and support the existing workflows:

- Probe local media and produce machine-readable output.
- Merge and remux local video/audio into the containers used by the wrappers.
- Preserve and write the required metadata.
- Convert the subtitle formats encountered by `vdl` to SRT.
- Handle and embed the thumbnail formats used by those workflows.
- On macOS, support `encode`’s current HEVC/VideoToolbox, AudioToolbox AAC, `mov_text`, scaling, stereo conversion, MP4 `hvc1` tagging, and `+faststart` behavior.

Use representative fixtures and actual postprocessing commands to determine the necessary codecs, muxers, parsers, bitstream filters, and filters. Keep `--disable-autodetect` and explicit feature selection. Every additional external library needs a concrete supported use.

Keep FFmpeg network-free. Support local file and local streaming protocols such as `pipe` or `fd` where the tested CLI operations require them. yt-dlp remains responsible for downloads; document the limitation on using FFmpeg itself as a network downloader.

Exclude `ffplay`, device capture, and desktop/audio-output stacks from the tools package. The Linux commands must work on a headless Alpine installation.

`encode` is presently Apple-specific despite living in the shared dotfiles layer: it uses `hevc_videotoolbox`, `aac_at`, and BSD `stat`. Preserve its macOS behavior and make the platform limitation clear, including a useful early failure on unsupported platforms if appropriate. Adding a Linux HEVC encoder or an external x265 dependency is outside this extraction.

Keep profile configuration explicit and readable. Two configurations with shared helpers are sufficient.

## 4. Make the producer independently buildable and its artifacts usable

Initialize `ffmpeg-build` with concise repository instructions, documentation, source pins, build/package scripts, focused checks, and CI.

The producer must build without a `play` checkout or an existing `usr` installation.

### Inputs and build identity

Verify downloaded source hashes, including cached downloads. Pin relevant toolchain/container inputs and preserve upstream attribution and notices.

Preserve the existing explicit FFmpeg `VERSION` handling: FFmpeg must report its upstream version rather than deriving a version from the surrounding repository’s Git tags.

Separate build directories by target and profile. Cache identity must include the source lock, recipe/patch identity, target, profile, relevant flags, and toolchain. A change to any of these must invalidate incompatible outputs.

Use small readable checked-in configuration. Generated JSON manifests are fine; avoid introducing substantial manually maintained metadata.

### SDK linkage and relocation

Keep FFmpeg static and make the SDK suitable for relocation and consumption outside the producer’s build directory.

Prefer ordinary PIC machine-code archives for the SDK. If any archive contains compiler-specific LTO bitcode, explicitly establish and test the consumer toolchain contract. Do not accidentally make the SDK usable only by the compiler that built it.

Package dav1d and zlib dependencies as appropriate, with complete static link information. Declare required Apple frameworks and Linux system interfaces such as libva accurately. Keep GPU drivers and unrelated desktop dependencies outside the SDK.

Generate working relative-prefix pkg-config files with correct private dependencies and framework flags. Confirm that `pkg-config --static` and an actual external link work after extraction into a different directory, including a path containing spaces.

Keep one consistent dependency closure in the final Player link. Reconcile existing dav1d/zlib recipes and any other consumers of zlib deliberately; avoid stale duplicate libraries from old prefixes.

Strip runtime executables appropriately. Preserve symbols needed to link SDK archives.

### CLI linkage

Produce fully static musl Linux CLI tools using the small required codec dependency set.

For macOS, statically link the private FFmpeg/codec libraries where practical and retain only the explicitly required system libraries/frameworks. The installed tools must run without Homebrew libraries.

Document and inspect the actual linkage. Apply any required macOS signing steps before producing the final archives and checksums.

### Artifact contract

Publish separate SDK and tools archives per target. A suitable naming convention is:

- `ffmpeg-<upstream-version>+<release-tag>-<target>-play-sdk.tar.gz`
- `ffmpeg-<upstream-version>+<release-tag>-<target>-tools.tar.gz`

Choose the final names once and implement them consistently in producer and consumers.

The SDK archive contains headers, libraries, pkg-config files, build/capability metadata, and notices. The tools archive contains the command pair, concise metadata, and notices; `usr` should not need to install development libraries.

Publish `SHA256SUMS` and concise per-artifact provenance. Metadata must distinguish target and profile and identify the source revision and build configuration.

## 5. Implement release CI in the style of `python-build`

Use its release discipline with a small FFmpeg-specific workflow.

Required flow:

1. Resolve the intended producer revision and release tag.
2. Build both profiles for all three targets.
3. Audit configuration, architecture, and dependency linkage.
4. Assemble final archives and checksums.
5. Extract those exact archives into fresh locations and qualify them.
6. Publish the complete passing release.

Follow the date/build-revision tagging convention. Existing `python-build` releases are prereleases, so make the new producer’s release status explicit and make consumers handle it correctly.

Never overwrite an existing release’s identity or replace its assets with different bytes. Use a distinct build revision when another release is needed on the same date.

Pin GitHub Actions to full commit SHAs and Alpine images to digests. Limit write permissions to publication jobs.

Qualification must cover the archives ultimately published. Do not test an intermediate installation and then independently rebuild the distributable.

For every SDK, compile and run a small external consumer against the extracted package. Verify useful library behavior and the configuration of the linked libraries. For every tools package, execute both commands and the applicable local-media fixture operations.

Test without access to the original build prefix. Use clean Alpine runtime environments for Linux. On macOS, demonstrate the absence of unintended Homebrew/runtime-prefix dependencies.

Provide documented local commands for building, auditing, packaging, and qualifying one target/profile. CI should invoke those same implementation paths.

## 6. Migrate `play` to a pinned SDK consumer

Normal development and release builds should acquire the `play-sdk` release artifact from `laputa-systems/ffmpeg-build`.

Implement a small checked-in dependency pin containing:

- The immutable producer release identity.
- The required profile and supported target mapping.
- Exact archive SHA-256 values.
- Any SDK contract/version information needed to reject incompatible artifacts.

Resolve the SDK from that pin, verify it before extraction, and install it into a target-specific dependency prefix. Cache by release, target, profile, and digest.

Make SDK upgrades an explicit documented operation. Normal Player builds must use the checked-in release identity.

Update all relevant paths:

- Development builds.
- macOS dependency and release builds.
- Linux container/dependency and release builds.
- Rust native linking and header/binding checks.
- CI caches and dependency stamps.
- Packaging, dependency audits, and documentation.

Pay particular attention to `rust/player-media/build.rs`. It currently discovers headers in fixed local prefixes, looks up dav1d separately, and contains Linux link assumptions outside the FFmpeg prefix. Have it consume the selected SDK and its declared dependencies correctly.

Scope FFmpeg discovery to the verified SDK so an unrelated system/Homebrew installation cannot satisfy it. Validate an explicit `FFMPEG_PREFIX` override against the same target/profile/ABI contract.

Ensure SDK/header changes trigger the necessary Cargo rebuilds. Preserve the relationship between the pinned FFmpeg headers and Player’s native bindings.

Move the authoritative FFmpeg recipe and component allowlists into `ffmpeg-build`. Remove the independent copies from `play` once the new path works. A thin consumer helper may preserve a convenient command, but normal builds must have one authoritative recipe.

### Preserve the audits

The existing FFmpeg manifest script reads `config_components.h` and `config.mak` from an in-repository build tree. A prebuilt SDK will change that assumption.

Generate authoritative configuration evidence in the producer and ship it with the SDK. Update Player’s audits to consume the verified artifact metadata and retain their meaningful restrictions.

Keep ownership clear:

- The producer validates its complete resolved component configuration.
- Player validates that it received the expected pinned playback profile and retains its application-level behavior checks.

Retain checks for the no-network boundary, absence of unwanted codec/program features, required playback capabilities, and expected dependency closure. Update source-layout assertions to reflect the new ownership rather than deleting the checks wholesale.

Player must remain independently runnable after installation. Its runtime must not depend on the `usr` CLI package, a global FFmpeg installation, or a sibling checkout.

The Linux Player may retain its documented dynamic musl desktop dependencies. Preserve the runtime behavior required by Wayland, Vulkan, ALSA, and libva.

### Handle test fixture generation separately

Audit any test scripts that invoke a general-purpose host `ffmpeg` to generate fixtures. Their test-only encoder requirements may exceed the shipped minimal tools profile.

Make that dependency explicit or use suitable deterministic fixtures. Avoid silently expanding the production tools package solely to satisfy a broad fixture generator.

## 7. Integrate the CLI pair into `usr`

Add a release-backed FFmpeg installer to `dl`, using:

`laputa-systems/ffmpeg-build`

At the inspected baseline, `usr` has no dedicated FFmpeg installer and no FFmpeg entry in its Brewfile or Alpine package lists. Recheck current HEAD before changing those files.

Use an explicit target mapping:

- `Darwin:aarch64` → `aarch64-apple-darwin`
- `Linux:x86_64` → `x86_64-unknown-linux-musl`
- `Linux:aarch64` → `aarch64-unknown-linux-musl`

Reject unsupported targets clearly. The generic `install_release` path contains GNU fallback behavior; keep FFmpeg selection explicitly musl-only.

Use existing installer conventions for download handling, portable hashing, XDG storage, managed-file ownership, and preserving working installations when update discovery fails.

The existing grouped Git installation is a useful model for managing several commands from one release.

### Install both commands as one unit

Make `sh dl ffmpeg` install or repair both `ffmpeg` and `ffprobe`.

Resolve one release identity once, then fetch its matching archive and checksum data. Verify, extract into a versioned staging directory, and smoke-test both executables before promoting the installation through a single current-version pointer.

Preserve the previous working pair on failure. Record ownership for both launchers and the installation directory. Respect existing unmanaged files and the repository’s uninstall semantics.

Check pair completeness when deciding whether an installation is current. A present `ffmpeg` with a missing or stale `ffprobe` must be repairable.

Handle prereleases deliberately. Do not assume GitHub’s `/releases/latest` endpoint will select a date-tagged prerelease. Use appropriate release enumeration or the repository’s compatible discovery convention, and verify the required assets are present.

### Wire default installation and health checks

Add the FFmpeg tools group to the default tool set on the supported platforms and to explicit dispatch.

Use Alpine’s existing `dl --list` / `sync tools` provisioning path. Keep one downloader and one source of truth.

Update the relevant completeness checks in:

- `host/alpine/install.sh`
- `host/alpine/verify.sh`
- `dotfiles/doctor`
- Installer ownership/reconciliation code.

Both commands must be detected and verified, including missing-sibling repair.

Keep the CLI pair usable in Alpine’s headless base installation. Installing it must not pull in Player’s desktop dependency set.

Verify that `encode` and yt-dlp’s postprocessing resolve the managed tools consistently. Preserve the existing Player installer and its supported platforms while ensuring it receives the newly built Player release during the final rollout.

## 8. Verify the integration with meaningful checks

Use existing test harnesses where possible. Add tests for the concrete packaging and migration risks.

### Producer checks

Verify all target/profile combinations, configuration restrictions, archive integrity, relocated SDK linking, and actual CLI operations.

Exercise wrong-target/profile rejection where applicable. Prove that the playback SDK retains its restrictions while the tools profile supports the additional operations it promises.

### Player checks

Run the existing applicable Rust, corpus, audio, seek, album-art, FFmpeg-audit, local-input, and release/dependency gates against the downloaded SDK.

Build both existing Player release targets from a clean dependency state. Check that neither the old FFmpeg source build nor a machine-installed FFmpeg can satisfy the build accidentally.

Compare meaningful artifact-size and dependency changes with the baseline and explain material differences.

### `usr` checks

Extend `dotfiles/dl-test.sh` for:

- The three explicit target mappings.
- Installation of both commands from one release.
- Repeat installation, upgrade, and missing-`ffprobe` repair.
- Failed checksum/extraction preserving the old installation.
- Managed ownership and unmanaged-file preservation.
- Default-tool selection and pair-completeness checks.
- Prerelease discovery and missing-asset handling.

Run the relevant shell and development checks for changed files.

Exercise the installed tools using temporary local media fixtures for probing, merging/remuxing, metadata, subtitles, and thumbnails.

Test `encode`’s actual options on Apple hardware when available. Distinguish encoder availability from successful hardware execution. Report any hardware-dependent checks that could not be run.

Use disposable fixture copies: `encode` intentionally trashes originals when the output is smaller. Run installation and provisioning tests in isolated temporary roots rather than modifying the working host.

## 9. Complete the rollout and report the result

Use this order:

1. Implement and qualify the producer.
2. Publish the first complete `ffmpeg-build` release.
3. Verify the released downloads and checksums.
4. Update Player’s SDK pin to that existing release.
5. Complete and verify `usr`’s tools installation.
6. Build and publish the corresponding Player patch release through its existing workflow.
7. Verify the resulting consumer installation paths.

Do not leave consumers referencing an unpublished tag or imaginary checksum. If publication or a required platform runner is unavailable, complete the implementation and identify the precise remaining blocker without claiming the release was verified.

Finish with:

- Commit IDs for each changed repository.
- Producer and Player release tags/URLs.
- The supported target/profile matrix.
- Artifact sizes and actual runtime dependency sets.
- Exact consumer installation/build commands.
- The supported CLI workflows and intentional feature limitations.
- Verification results, with hardware/environment gaps stated precisely.
- A concise explanation of how to update FFmpeg and propagate a future SDK release.

The completed state should have one authoritative FFmpeg build repository, a pinned minimal SDK consumed by Player, and a checksum-verified FFmpeg/ffprobe pair installed by `usr` on Apple Silicon macOS and both supported Alpine/musl architectures.
