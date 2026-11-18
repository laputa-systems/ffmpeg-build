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


Tests (DSLP-4) branch coverage baseline at `189a083` used coverage.py 7.17.3
and all 76 controller tests on macOS ARM64. `make coverage` measured
746 of 1,466 statements and 313 of 588 branches across `build.py`,
`bootstrap.py`, and the release assembly script. The normal suite passed
twice, each in 1.19 s under `cpu-guard --cores 2` with a warm environment.

The controller suite covers profile and lock validation, wheel cache reuse,
archive layout, and release asset assembly. It uses sealed stage fixtures
and runs separately from native qualification. Compiler and dependency build
paths, runtime archive probes, and the top-level CLI dispatch remain outside
the ordinary checks. The missing CLI assertions and the stage-provenance
finding remain open. This coverage baseline measures execution. The
mutation selection and survivor dispositions are still required for DSLP-4.


Release archive acceptance at base `bde17f5` selected the 35 mutations in
`archive_commit` with mutmut 3.8.1 and pytest 9.2.0 on macOS ARM64.
The original tests caught 28. The added cases catch the other seven:
r:xz replaced by automatic compression, two lost missing/non-file diagnostics,
two lost malformed-object diagnostics, and two changes to the missing producer
default. All 35 now have exit code 1 from their tests. Four direct controls
checked wrong compression, an absent producer, the malformed-object diagnostic,
and the missing-member diagnostic. Reverting the controls restored all nine
release tests. The full uninstrumented controller suite passed 79 tests.

To reproduce, unpack `git archive HEAD` into a fresh directory under
`.work/tmp`. Populate its `.work/cache/sources` with the verified wheel
from a normal `make test`. Copy `.github/scripts/assemble_release.py`
byte-for-byte to `ci/release/assemble_release.py` in that directory. Adjust
the release test's `spec_from_file_location` name and path to
`ci.release.assemble_release` and `ci/release/assemble_release.py` in
the scratch copy. Append the following to its `pyproject.toml`:

```toml
[tool.mutmut]
source_paths = ["ci/release/assemble_release.py"]
also_copy = ["tests", "build.py", "bootstrap.py", "sources.lock.json", "profiles", ".work/cache/sources"]
pytest_add_cli_args_test_selection = ["tests/test_assemble_release.py"]
use_setproctitle = false
```

From that directory with a repo-owned `TMPDIR`, run
`cpu-guard --cores 2 -- uv run --frozen --with mutmut==3.8.1 --with pytest==9.2.0 python -m mutmut run --max-children 1 '*archive_commit*'`.
Read the 35 matching keys in `mutants/ci/release/assemble_release.py.meta`
under `exit_code_by_key`. The alternate import path matches mutmut's
module naming. The wider release functions and controller remain open.


The whole release assembly script at `afe69a3` generated 153 mutations
under the same setup with the function selector omitted. Before the command
and assembly assertions, 97 were caught, 14 survived, and all 42 in the CLI
entry point had no tests. The new assertions catch 149 of the same 153.
Three survivors are equivalent for the declared artifact inputs:
`check_manifest` mutation 5 splits a stem with one exact version separator;
`assemble` mutations 36 and 38 pass a falsey value or omit the default-false
`exist_ok` argument. `main` mutation 16 uppercases the lock filename. Both
spellings resolve to the same inode on the local macOS volume. The
case-sensitive Linux ARM64 trial caught that identity and reconciled all 153,
with 150 caught and the same three equivalents. [Hosted run](https://github.com/laputa-systems/ffmpeg-build/actions/runs/44296342661)

The earlier archive-commit test changed the sidecar and the archive together,
so the sidecar rejected the fixture first. The updated fixture changes only
the archive commit. Direct controls also cover incorrect output-directory
creation, usage status, duplicate and missing assets, the sidecar diagnostic,
and preservation of an existing destination. The 82-test ordinary suite
and Ruff and ty passed.


The controller process tests cover the locked version, invalid profile
target, and missing package flag. A wrong version, false success status,
and optional profile flag each failed its own test. Restoring the controller
passed all three controls and the 85-test suite. The subprocess coverage
run combined four files and measured 774 of 1,466 statements and 325 of
588 branches. Native build and qualification paths retain separate checks.


Packaging now uses the audit and qualification source-pin check before
writing the archive or sidecar. The DSLP-6 witness failed on the prior
revision and now rejects a stale dav1d digest with the staged manifest
unchanged and no output directory. A valid tools stage produced identical
archive bytes before and after. All 86 tests and both linters passed.


Package mutation at `4bf7f06` selected 186 identities in `package` and
`mismatched_source_pins`, using mutmut 3.8.1 and pytest 9.2.0. The base caught
134 and the new stage fixtures caught 181. Four remaining identities uppercase
one stage path component or the lock filename on the case-folded macOS
volume. One changes the missing commit default from an empty string to
`XXXX`. Both fail the same 40-character lowercase hexadecimal check. The
case-sensitive Linux ARM64 run caught all four, for 185 caught and one
commit-default equivalent at the exact trial head `87634f5`.
[Hosted run](https://github.com/laputa-systems/ffmpeg-build/actions/runs/44300718449)

Reproduce with the scratch archive and cached wheel described above, leaving
`build.py` at the root. Set `source_paths = ["build.py"]` and
`pytest_add_cli_args_test_selection = ["tests/test_build.py"]`, and omit
`build.py` from `also_copy`. Select `'*x_package__mutmut_*'` and
`'*x_mismatched_source_pins__mutmut_*'`. The ordinary controller suite passed
90 tests. Subprocess coverage measured 794 of 1,472 statements and 333 of
590 branches.


Qualification now exercises an extracted tools archive and its manifest with a
controlled native script result. The test checks the selected script and path
with spaces, locked source pins, malformed JSON, and non-normalized metadata
that must stop before extraction. Forcing the script's failed exit to pass
reproduced a false success and failed the new test. Across identical source at
`53d427e`, mutmut selected 359 `qualify`, `archive_member_problems`, and
`read_manifest` identities under the package setup above. The base caught
25, with 10 live and 324 lacking tests. The new case caught 240, with 119 live.
The breakdown is 193/285, 27/35 and 20/39 caught, respectively. The survivors
remain open, including special profiles, runtime-library checks and archive
member paths. The 91-test suite passed with 857/1,472 statements and 342/590
branches covered. Native producer/consumer checks retain their manual release
boundary and were not executed by the test.

## Tickets



### DSLP-4 · P2 · Tests: coverage, boundary gaps, mutation

- **Area:** deslop · tests
- **Where:** test suites and CI
- **Problem:** Coverage and scoped assembly, packaging and qualification mutations are measured above. Qualification survivors, native effects, and a fail-closed whole-change mutation lane remain open.
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
