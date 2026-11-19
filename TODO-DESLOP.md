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


The malformed-stage fixture at `69373f4` reproduced an array accepted by
`read_manifest` and an invalid JSON traceback from `package`. Stage audit,
qualification and packaging now share the object parser. Both cases emit an
operator diagnostic, with staging bytes intact and no archive output. The full
92-test suite, Ruff and ty passed. The earlier mutation identities remain
historical because this change modifies `read_manifest` and `package`.


Runtime qualification now uses sealed library trees for macOS ARM64 and Linux
x86-64 musl. Valid archives pass, while a changed library or an internal link
pointing to another library fails. A Linux test-only archive selects its own
fixture qualification script. Disabling the library check and selecting the
normal script made both new tests fail. No shipped binary was executed.

At `4bd6076`, matching source selected 368 identities using the package mutation
setup above with `qualify`, `archive_member_problems`, and
`extracted_library_problems`. Baseline catches were 193/285, 27/35 and 30/48.
The new cases caught 221/285, 27/35 and 34/48, or 282 total. Respectively 64,
8 and 14 survived. The 94-test suite and both linters passed. Those survivors
and native qualification remain open.


Qualification now rejects individual mismatches in the staged profile,
target, source version, producer commit and release filename, plus a missing
contract field. Bypassing target identity returned a false success and failed
the new target case. On `75fb9ff` the two runs selected the same 285
`qualify` identities. The new cases caught 245, up from 221. The 40 live IDs
are 40, 49, 55, 56, 59, 60, 62, 64, 69, 80, 85, 86, 179, 192, 196,
198–204, 208, 209, 211, 214, 216–221, 223, 237, 239, 244, 250, 251,
254 and 255. All 95 ordinary tests, Ruff and ty passed. The remaining
archive and native verification scopes stay open.


The qualification follow-up at `cf63e30` checks XZ compression, explicit
archive extraction filtering, missing documentation and runtime inventory,
and bounded diagnostics for changed files. Disabling the notice check and
using format auto-detection independently failed the added cases. Across the
same 285 `qualify` identities, the prior suite caught 245 and the follow-up
caught 284. ID 179 is equivalent because both missing-commit defaults fail
the same required lowercase hexadecimal match. All 97 ordinary tests and both
linters passed. The neighboring archive-member and library helpers, native
qualification, and the whole-change gate have independent open scope.


The archive and runtime-library helpers at `6bd80b4` now have independent
checks for owner/group metadata, member type, foreign roots, missing and
unrelated files, and a missing Mach-O identity. The owner/group check and the missing-file fallback
each failed a direct control. The same 83 identities moved from 63 to 81
caught. `extracted_library_problems` catches all 48. `archive_member_problems`
catches 33 of 35. Replacing `False` with `None` for the membership flag (ID 6)
leaves its only truth test unchanged. Including the supported root directory
as a relative candidate (ID 16) has no effect because regular-file and link
checks both ignore directories. Root shape validation outside that declared
input stays separate. The full 99-test suite and both linters passed.


The stage reader follow-up at `e25d04e` verifies the exact failure path and
success result. Treating an absent file as readable fails the added case.
The current package, source-pin, stage parser and reader selection contains
232 identities. The new reader case moves the count from 211 to 225 caught
on macOS, including all 17 source-pin and all six parser identities. Reader
IDs 13 and 24 replace a false flag with `None`. `Audit.case` treats both the
same for the status, diagnostic and result tally. Package ID 89 substitutes
an equally invalid missing-commit value. Package IDs 30, 32, 34 and 167
alter path case. The Linux ARM64 trial at `600b2a2` caught all four, for
229 caught and the three equivalents. All 100 tests and both linters passed.
[Hosted run](https://github.com/laputa-systems/ffmpeg-build/actions/runs/44311448379)

The controller `main` selection at base `7e6b357` uses direct calls to the
real parser with sealed dispatch fixtures, alongside the existing subprocess
checks. It checks required arguments, help, version output, Python version
rejection, dispatch arguments and return statuses. A separate archived fault
that changed the audit return to zero failed the audit dispatch assertion
(`0 != 17`). No native binary or download was invoked.

With mutmut 3.8.1 and pytest 9.2.0, a fresh archive selected exactly 104
`build.x_main__mutmut_*` identities: 102 killed (exit code 1), two survived
(exit code 0), and none timed out or lacked tests. A fresh repeat after
review gave the same two identities. ID 1 changes `< (3, 12)` to `<=`.
The interpreter exposes a five-element version tuple, so comparing it with
a two-element tuple can never yield equality. [Python version metadata](https://docs.python.org/3/library/sys.html#sys.version_info)

ID 104 changes the unreachable terminal return from 2 to 3. The required
subparser accepts only `version`, `qualify`, `fetch`, `build`, `audit` and
`package`, and each branch returns. The invalid command process test exercises
the parser's own status 2 before dispatch. These two identities are equivalent
for the declared interpreter and CLI paths. Fetch, native build, and the
whole-change gate remain open. All 107 tests, Ruff and ty passed.

To reproduce, archive this commit into a fresh directory under `.work/tmp`,
copy the verified `laputa_buildlib-0.1.0-py3-none-any.whl` to its
`.work/cache/sources`, and append the following to its `pyproject.toml`:

```toml
[tool.mutmut]
source_paths = ["build.py"]
also_copy = ["tests", "bootstrap.py", "sources.lock.json", "profiles", ".work/cache/sources"]
pytest_add_cli_args_test_selection = ["tests/test_cli.py"]
use_setproctitle = false
```

Install the pinned tools into an ignored `.work/venv` from the restored mirror,
set `TMPDIR` to the worktree's `.work/tmp`, and run from the archive with a
120-second timeout: `cpu-guard --cores 2 -- <worktree>/.work/venv/bin/python -m
mutmut run --max-children 1 '*x_main__mutmut_*'`. Count the matching keys and
their `exit_code_by_key` values in `mutants/build.py.meta`. The initial
subprocess-only baseline could not associate tests with the mutated function;
adding the direct parser tests recovered the run and produced 88 killed and
16 survivors before the final parser assertions.

Release collection at `8e663213c4e352e48fe22c97a6727e0b48bb1b09`
raised a raw `AttributeError` through the command when a sidecar contained
valid JSON with a list root. The fixture writes the complete local asset
inventory that the command ordinarily consumes. The parser now rejects a
non-object root with the sidecar name before creating the destination.
The same command fixture passes on the candidate, with exit 1, no output
directory or stdout, and the expected error on stderr. The valid fixture
still assembles all ten products with verified checksums. No release ran.

The release collector and locked wheel bootstrap passed a case-sensitive
[Linux mutation trial](https://github.com/laputa-systems/ffmpeg-build/actions/runs/44317939755)
at `037466b1bbdc95e8f827bfd6130800af6b56f24d`. This trial uses the same
production files as `6f074f2636436933ed000916ed9fe33ccd7e0e8e`, with exact
invalid-lock diagnostics in the bootstrap tests. Mutmut 3.8.1 and pytest
9.2.0 classified all 155 collector identities and all 75 bootstrap
identities with one worker. The collector caught 152 and the bootstrap
caught all 75. The bootstrap had caught 40 of the same 75 in the prior
baseline. Exact diagnostics catch the three message-only survivors.
Linux distinguishes the two case variants of the lock and staging names.

Collector IDs `x_assemble__mutmut_36` and `x_assemble__mutmut_38` are
equivalent for `Path.mkdir`: `None` is falsey and an omitted `exist_ok`
defaults to false. `x_check_manifest__mutmut_7` is equivalent on the
workflow's supported filename inputs. The pinned numeric version occurs
once in each declared stem between its profile and target, so
`partition` and `rpartition` split there. The unsupported manual version
strings are outside that workflow's naming contract.

Reproduce using the
[sealed trial workflow](https://github.com/laputa-systems/ffmpeg-build/blob/037466b1bbdc95e8f827bfd6130800af6b56f24d/.github/workflows/deslop-collector-trial.yml).
The collector production file is copied byte for byte to
`workflow/scripts/` in the archive, so mutmut can assign importable
module names. Only the disposable test copy changes its import to match.
No native build or release ran.

Build stamp recovery at `004297dd46600ffb592fc630c20cd95ae6aeb1f8`
used an otherwise complete tools stage. A JSON list, truncated JSON
and undecodable UTF-8 each stopped the build before source acquisition.
A matching object stamp still reuses the stage with no fetch. The
candidate retries source acquisition for each corrupt stamp and leaves
the stage and stamp intact if that fetch fails. The test uses the real
stage completeness and fingerprint checks and stops at the acquisition
boundary. Run `uv run --frozen python -m unittest discover -s tests -p test_build.py -k corrupt_build_stamp`.
Native compiler and source download operations were not run.

The native x86-64 Linux runtime artifact passed
`make build verify TARGET=x86_64-unknown-linux-musl PROFILES=runtime`
at trial head `e3a31ab3438969d6c27c9d322d512268217247da` with the locked
inputs. The archive audit passed 145 checks during the build. The
fixture verifier passed 55 media workflows against both the staged and
unpacked binaries. The unpacked runtime also linked an external consumer,
decoded H.264 and AV1 through the shared libraries, and passed its 14
archive and manifest checks. The `ffmpeg-runtime-9.0.2-x86_64-unknown-linux-musl.tar.xz`
SHA-256 was `a72dfd058ada8f22be12013d641ca4fbb5feeecceb734dedbfb06d5b31e8e8b0`.
No release was published. Other profile and target combinations remain
outside this run. [Hosted runtime run](https://github.com/laputa-systems/ffmpeg-build/actions/runs/44333488976)

The native ARM64 macOS run at `d1b6ee5bc264510f5847c1923fafc5f969db8ac1`
passed `make build verify TARGET=aarch64-apple-darwin` with Xcode 27.2
(27B52), Python 3.15.2 and two compiler jobs. Generate the fixture media
first with `scripts/linux-fixtures.sh` in the pinned ARM64 image. The
SDK and runtime both linked their external consumers and decoded H.264
and AV1. The tools and runtime passed all 55 media workflow cases.
This is a local artifact run with the installed Xcode, alongside the
separate release workflow that selects Xcode 27.1.

Native ARM64 Linux at trial head `4fd1ee747f6eacb6800ec2d0e53ad74a4a15052f`
also built, audited and verified all three profiles using the release
inputs. The static SDK, tools media workflows and external shared-library
consumer all passed. [Hosted ARM64 qualification](https://github.com/laputa-systems/ffmpeg-build/actions/runs/44336453427/job/134914388704)

Native x86-64 Linux at the same trial head passed all four profiles,
including the test-only fixture tools, which passed their 13 packaged
checks. The SDK, production tools and runtime passed the corresponding
consumer and media checks. [Hosted x86-64 qualification](https://github.com/laputa-systems/ffmpeg-build/actions/runs/44336453427/job/134914388130)

| Target | Profile | SHA-256 |
| --- | --- | --- |
| ARM64 macOS | play-sdk | `68bb8a5f39f52b0516950a79253c932628ea341443ac28db4dc464d727776e3e` |
| ARM64 macOS | runtime | `973ae984bbedef16986c5e9bc886aab028eb0120e2d1f008b68203e49e277a1e` |
| ARM64 macOS | tools | `b7c62de112b6274a2dfc0214d3ca68784947312c616e8f4269ccdda52f46ba0a` |
| ARM64 Linux musl | play-sdk | `2f9ea9dcc50aa66bc23013315a4389841e760863a07f758dce5a98ac7458f2c8` |
| ARM64 Linux musl | runtime | `04c1657d358e5c31440198ebac337ba9926a7c35b9b2198ac717f67e16ea58bd` |
| ARM64 Linux musl | tools | `41edbbc9d6fff2bb96374102cb6201a7d0b89c8ea58d8cbdb4fd81901ab025ec` |
| x86-64 Linux musl | fixtures | `147b9aa1ad592544d59f31da18ba18bcebd15f4948f04238879c33efefcac71f` |
| x86-64 Linux musl | play-sdk | `7a97ed0a4f1884dfed26bf5c9ace009248eebbb597659545f3efe5c4f151acc9` |
| x86-64 Linux musl | runtime | `b805e70d9b8116c1e7a0ec868b77b16acc32b6071be53a071cb8c28259f9470b` |
| x86-64 Linux musl | tools | `47b1dc2ff67140925c827e6dc747382076281b66954cab178233145baa025458` |

The runtime library and binary inspection slice at `82bcb481` accounted
for all 218 identities in `library_layout`, `versioned_library_pattern`,
`library_identity_name`, `elf_dynamic`, and `macho_load_commands`.
The baseline caught 202 and left 16 survivors. The candidate caught
all 218. The generated production files matched byte for byte.

The layout fixture confirms a duplicate versioned library does not
hide other libraries or unclaimed symlinks. The ELF fixture checks an
uppercase hex tag, legacy multi-entry RPATH, standalone TEXTREL,
unrelated bracketed metadata and absent SONAME. The Mach-O executable
fixture verifies the absence of an install name.

Use the existing scratch mutation recipe and select
`tests/test_build.py -k 'LibraryLayoutTests or BinaryInspectionTests'`.
Run the five function patterns above with one worker under mutmut 3.8.1
and pytest 9.2.0. All 115 ordinary tests, Ruff and ty passed. The
whole-change workflow remains open.

The native runtime loader audit at `511b46b3` now has sealed ELF and
Mach-O command fixtures for both programs and shared libraries. They
check CPU and file identity, dependencies, relocation paths, stack
size, musl interpreter, code signatures, and bounded failure details.
The separate packaged native runs remain the real-tool evidence.

The first fixture set caught 275 of 305 mutations. Exact failure details,
an independent ELF file-kind mismatch, a profile framework and bounded
symbol diagnostics caught all 30 remaining identities. Both generated
sources compared byte for byte. Run mutmut 3.8.1 and pytest 9.2.0 with
one worker in the usual sealed controller layout. Select
`tests/test_build.py -k RuntimeLinkAuditTests` and the function patterns
`x_gnu_stack_size`, `x_audit_runtime_elf`, and `x_audit_runtime_macho`.
The full 117-test suite and both linters passed.

The full `build.py` mutation inventory at
`aa4f74741638ef3762a324b2e687b1509b0c62f1` has 5,600 identities.
On macOS ARM64, mutmut 3.8.1 and pytest 9.2.0 recorded 2,124 test
failures, 664 survivors, and 2,812 identities with no test
selection. Neither no-test entries nor survivors count as catches.
The largest no-test groups are the audit dispatcher (696), runtime
audit (373), SDK audit (288) and tools audit (232). Native runs exercise
those paths against real artifacts. The ordinary test gate still needs
controlled stage cases that detect audit failures.

To reproduce the inventory, use the scratch recipe for `build.py`
above, add `patches`, `scripts`, `Makefile` and `.github/scripts` to
`also_copy`, and select `tests/test_build.py` and `tests/test_cli.py`.
Run `mutmut run --max-children 1 'build.*'` and classify all
`exit_code_by_key` entries in `mutants/build.py.meta`. Mutmut's exit code
33 identifies entries with no selected tests in this version.

Audit and package both parse the staged manifest. Previous validation
accepted a list for the source or producer map, a null source record,
and a numeric producer commit. Downstream package access then failed
outside its normal diagnostics. The parser now rejects those records,
and the fixture checks both diagnostics, intact input bytes, and the
absence of output. Missing fields still use the existing consumer
checks.

The shared audit fixture reads a tools build tree and staged manifest.
The valid case exercises the shared audit and its handoff to the
binary checks. Four changes cover commit identity, effective network
configuration, LTO flags and the resolved encoder set. Each reports
the expected failures. The binary handoff uses a test double here;
the native profile checks exercise the actual binaries.

Reusing the exact 696 audit identities from the full inventory, the
fixture selected all 696, with 376 test failures and 320 survivors.
Use the same scratch archive recipe, select
`tests/test_build.py -k inconsistent_build_tree`, and run
`mutmut run --max-children 1 'build.x_audit__mutmut_*'`. The audit
implementation is byte-for-byte identical. The remaining identities
are still open. All 118 ordinary tests and both linters passed.

The staged manifest reader now rejects non-object toolchain records
and non-string compiler, sysroot, CPU baseline or libc fields. At
`0de54ca`, the audit fixture reproduced attribute errors for a toolchain
list and a null libc value. The reader and package tests now check
the field diagnostics, preserved manifest bytes and absence of output.

The same 696 audit identities moved from 376 to 386 catches. The
audit function is unchanged. Additional cases vary the manifest
contract version, profile, target and pinned source checksum
independently. Use the existing `inconsistent_build_tree` selection
above to reproduce the comparison.

Runtime qualification now diagnoses malformed library records
at the manifest reader. With the previous reader, list and null
records produced attribute errors while invalid file and link
values could raise type errors. The new cases use actual archives
of both runtime manifest shapes and assert the field diagnostic.
The fixtures also retain checks for valid records, missing metadata,
changed bytes and incorrect symlinks.

Run `python -m unittest test_build.StageTests.test_qualify_runtime_checks_extracted_library_bytes_and_links`
with `PYTHONPATH=tests:.` in the locked environment. The fixtures
mock the native script and verify the extraction and manifest
paths. The 118 ordinary tests, Ruff and ty passed.

The runtime build-tree fixture now checks shared-only configuration
and the runtime audit handoff. It reads the resolved file protocol,
AV1 decoder and the four Linux VAAPI accelerators from the actual
config header. The passed arguments include both the requested and
the parsed lists in their own order, and the checked stage manifest.
Disabling shared libraries or enabling static libraries each produces
the same scoped audit failure. The native artifact trials above
exercise the real loader and binaries.

At `a9ebce0aed380a8201ad5482c7b94f76864e8f89`, the same 696
`audit` identities moved from 386 to 437 caught with no other outcome
changes. Use Python 3.15.2, mutmut 3.8.1 and pytest 9.2.0 with the
same archive recipe above. Select
`tests/test_build.py -k 'inconsistent_build_tree or audit_runtime_checks_shared_configuration'`
and `build.x_audit__mutmut_*`. The remaining 259 survivors stay in
DSLP-4. All 119 ordinary tests, Ruff and ty passed.

The SDK audit fixture now reads the macOS build-tree header with
the target's VideoToolbox accelerators. The matching manifest
continues through the SDK audit handoff. Adding an effective
encoder or muxer independently changes the expected audit status
and identifies the forbidden component class. The fixture doubles
the final binary inspection. The native artifact receipts record
the real SDK checks.

The unchanged `audit` selection at `1fb8b5fe` caught 470 of 696
identities using the preceding recipe and adding
`audit_sdk_rejects_effective` to the pytest selector. The preceding
437-catch result used the two existing build-tree fixtures. All
120 ordinary tests, Ruff and ty passed. The remaining 226 outcomes
are under DSLP-4.

The common audit fixture now changes the staged manifest fields
independently of the matching tools build tree. It exercises resolved
components, automatically enabled components, library sets, framework
and dependency lists, configure records, license, and all required
toolchain strings. Each case checks the failure for its own field.

At `3bd56466f7208c0b385fa962fa700291418db000`, the same 696 audit
identities moved from 470 to 502 catches. All previous catches held.
Reproduce with the same three-test selector above. All 120 ordinary
tests, Ruff and ty passed. DSLP-4 retains the 194 remaining outcomes.

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

Bootstrap cache mutation at base `644c6ff72533b2a955d2116aa8d51583e7faabed`
selected the same 75 `_wheel` and `_digest` identities in fresh before and
candidate archives on macOS ARM64, with mutmut 3.8.1 and pytest 9.2.0. The
before results were 40 caught (exit 1) and 35 survived (exit 0); the candidate
results were 70 caught and five survived, with no other result classes. A
local-byte transport fixture exercises cache miss, hit, replacement, bad
bytes, and transport failure. Reversing the staged digest comparison in a
separate archive made the download test fail on the valid fixture.

Five outcomes remain unresolved: `_wheel` IDs 5 and 62 change the case of
`sources.lock.json` and `.part`; this volume resolves those spellings to the
same files, so a case-sensitive run is needed. IDs 8, 16 and 20 surround the
three malformed-lock diagnostics with `XX`; the tests check the diagnostic
substring, not exact spelling. These are diagnostic-only survivors, not
claims of equivalence. Native builds, actual network downloads in these tests,
and the wider DSLP-4 mutation scope remain open.

To reproduce, make two fresh directories under `.work/tmp` and unpack
`git archive 644c6ff72533b2a955d2116aa8d51583e7faabed` into each. Copy this
commit's `tests/test_bootstrap.py` into the candidate only. Run normal
`make test` in the worktree to fetch the pinned verified buildlib wheel, then
copy `.work/cache/sources/laputa_buildlib-0.1.0-py3-none-any.whl` to the same
relative location in both archives. Append this configuration to each
archive's `pyproject.toml`:

```toml
[tool.mutmut]
source_paths = ["bootstrap.py"]
also_copy = ["tests", "sources.lock.json", ".work/cache/sources"]
pytest_add_cli_args_test_selection = ["tests/test_bootstrap.py"]
use_setproctitle = false
```

Install mutmut 3.8.1 and pytest 9.2.0 from the mirror in `.work/venv`. From
each archive, set `TMPDIR` to the worktree's `.work/tmp` and run
`timeout 120 cpu-guard --cores 2 -- <worktree>/.work/venv/bin/python -m mutmut run --max-children 1 '*x__wheel__mutmut_*' '*x__digest__mutmut_*'`.
Compare the keys and `exit_code_by_key` values in `mutants/bootstrap.py.meta`;
the command's success alone does not classify survivors.
