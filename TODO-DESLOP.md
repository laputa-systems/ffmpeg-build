Prefix: DSLP
Next: 7

Deslop campaign backlog ([plan](https://github.com/laputa-systems/stuff/blob/main/docs/campaigns/deslop.md), tier A). One agent works this file with the `deslop` skill: take the lowest-numbered open ticket whose area does not start with `Needs owner ·`. After DSLP-5, work the open P1 and P2 findings, then fill in `## Report` below.

## Report

Ground (DSLP-1) passed on macOS ARM64 at base `539141d40ffecd42c1eada9abaea1475927a7cf0`; PR #7 merged as `689ca3a595450d1840f9812a3e5384559fc28b01` with test and lint checks successful. [Verification](AGENTS.md#verification) records costs, contracts, consumers and gaps.

Diagnose (DSLP-2) reviewed the first-party controller and profile validation, stage and archive checks, release assembly/provenance, unit and qualification tests, profiles, and existing docs at `689ca3a`. Baseline `make test` passed 73 tests and `make lint` passed Ruff and ty. `mdtool check` reported 0 errors, 38 warnings and 70 notes, largely historical or cross-repository references. `docs/artifacts.md` now includes fixtures in GPL notices and license descriptions and describes the profile-specific source list. Existing FFB-1 was not duplicated.

Filed DSLP-6 (P2, assumed): a sealed temporary tools stage contained every required notice and program placeholder, a valid current producer commit, the locked FFmpeg version and a dav1d digest of 64 zeroes. With only `build_paths` and `DIST` redirected to that fixture, `build.package("aarch64-apple-darwin", "tools")` returned successfully; the archive retained the zero digest while its sidecar held the current lock digest. `build.py:1984-2016` explains the result, and `build.py:2121-2126` shows the later qualification guard. The regular package test at `tests/test_build.py:174` does not check stale dependency pins.

Limits: no native media builds, artifact qualification scripts, release, upstream downloads beyond normal baseline setup, dependency or upstream code review, or external consumer runs. A sealed up-to-date build fixture also retained its original producer commit across a documentation-only revision; that accurately describes the build and was not filed as a separate defect. DSLP-4 and DSLP-5 remain for their later scopes.

Types (DSLP-3), scoped to bootstrap and release assembly at `32535b71`: adopted ty `unsound-return-statement = error`. The baseline had three diagnostics: two wheel `Path` returns inferred from `Any`, and archive commit `Any` returned as `str | None`. The source pin now checks the JSON object, inputs, filename, URL and digest before cache or network use; archive assembly checks the manifest, producer and optional commit. Malformed values fail explicitly; missing commit still returns `None`. Sealed tests use a local cache and archive, forbid network access, and fail against the original implementation. Restoring the original two files under the adopted rule reproduces exactly those three diagnostics. The first-party Python escape-hatch count (`cast`, `Any`, ignores and noqa) is unchanged at 3.

Measured with pinned ty 0.0.101 and Ruff 0.17.4: ty `missing-type-argument`, `unused-ignore-comment`, `blanket-ignore-comment`, `disjoint-cast`, `dynamic-function-decorator-return`, `possibly-unresolved-reference`, `unsound-yield` and `unsupported-dynamic-base` each found 0; `unsound-assignment` found one temporary boundary assignment during implementation and 0 after narrowing. Ruff `ANN401`, `PGH003`, `TC`, `B` and `RET` found 0; `ANN` found 446 initially (447 after the new test helper). These settings were not adopted: zero findings provide no defect witness, and the broad annotation family concerns unrelated untyped internals. Those internals remain deferred; green ty does not prove them sound. No full build, external consumer qualification, or release was run; the release assembly tests exercise the candidate directly. DSLP-6 remains independent.

## Tickets



### DSLP-4 · P2 · Tests: coverage, boundary gaps, mutation

- **Area:** deslop · tests
- **Where:** test suites and CI
- **Problem:** Coverage and mutation results are unmeasured; no deslop mutation lane exists.
- **Recommendation:** Run the deslop Tests step. Accept: no undispositioned survivor in critical code, the test cost budget holds, and the lane is green where the tools are mirrored.
- **Fix with:** deslop
- **Effort:** M

### DSLP-5 · P2 · Dead code: tools and debloat

- **Area:** deslop · dead code
- **Where:** whole repository
- **Problem:** No dead-code scan has run.
- **Recommendation:** Run the deslop Dead code step. Accept: tools clean or allowlisted with reasons; walk-backs filed as Needs owner tickets.
- **Fix with:** deslop
- **Effort:** M


### DSLP-6 · P2 · Packaging can attest a lock that did not produce the stage

- **Area:** artifact provenance
- **Where:** build.py:1984, build.py:2008, build.py:2119, tests/test_build.py:174
- **Problem:** package checks only the staged FFmpeg version before writing the current sources.lock.json digest into the sidecar; it does not compare the stage's dependency hashes with that lock. A sealed tools stage with a dav1d SHA-256 of 64 zeroes, otherwise matching the current FFmpeg version and producer commit, passed build.package and produced a sidecar claiming the current lock digest. A stage left over after a dependency pin changes can therefore acquire a misleading provenance sidecar. qualify later checks source hashes, but package is also a standalone documented operation and its sidecar is already emitted.
- **Recommendation:** Before writing the archive and sidecar, reject a stage whose recorded sources do not match the current profile's lock entries; cover a stale dependency pin with a sealed package fixture. Preserve the producer commit as the build's actual revision.
- **Fix with:** durable-state
- **Effort:** S

