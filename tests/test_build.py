import io
import json
import pathlib
import subprocess
import sys
import tempfile
import tomllib
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build
from bootstrap import hashing, release


class ProfileTests(unittest.TestCase):
    def test_profiles_declare_target_scope(self):
        for name in ("play-sdk", "tools", "runtime"):
            profile, _ = build.load_profile(name)
            self.assertTrue(profile["targets"])

    def test_play_sdk_macos_components(self):
        profile, _ = build.load_profile("play-sdk")
        requested = build.requested_components(profile, "aarch64-apple-darwin")
        self.assertEqual(requested["protocols"], ["file"])
        self.assertIn("libdav1d", requested["decoders"])
        self.assertIn("h264_videotoolbox", requested["hwaccels"])
        self.assertIn("hevc_videotoolbox", requested["hwaccels"])
        self.assertNotIn("encoders", requested)
        self.assertNotIn("muxers", requested)

    def test_source_pins_have_sha256(self):
        lock = build.load_sources()
        for source in lock.values():
            self.assertRegex(source.sha256, r"^[0-9a-f]{64}$")

    def test_sources_lock_follows_the_build_contract(self):
        raw = json.loads((build.ROOT / "sources.lock.json").read_text())
        self.assertEqual(raw["schema_version"], 1)
        names = [source["name"] for source in raw["inputs"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(list(build.load_sources()), names)
        for source in raw["inputs"]:
            self.assertTrue("url" in source or "urls" in source, source["name"])

    def test_buildlib_pin_matches_the_lock(self):
        pyproject = tomllib.loads((build.ROOT / "pyproject.toml").read_text())
        pinned = build.load_sources()["laputa-buildlib"]
        self.assertIn(f"laputa-buildlib=={pinned.version}", pyproject["project"]["dependencies"])
        self.assertTrue(pinned.extra["filename"].startswith(f"laputa_buildlib-{pinned.version}-"))

    def test_mov_text_configure_alias(self):
        self.assertEqual(build.configure_component("decoders", "mov_text"), "movtext")

    def test_component_problems(self):
        requested = {"decoders": ["h264"], "protocols": ["file"]}
        resolved = {
            "decoders": ["h263", "h264"],
            "protocols": ["file", "http"],
            "encoders": ["aac"],
        }
        problems = build.component_problems(requested, resolved)
        self.assertTrue(any("encoders" in problem for problem in problems))
        self.assertTrue(any("network protocols" in problem for problem in problems))

    def test_auto_selected(self):
        requested = {"decoders": ["h264"]}
        resolved = {"decoders": ["h263", "h264"]}
        self.assertEqual(build.auto_selected(requested, resolved), {"decoders": ["h263"]})

    def test_host_cpu_flags_only_in_compile_variables(self):
        config_mak = (
            "CFLAGS=-O2 -march=armv8-a\n"
            "NVCCFLAGS=--cuda-gpu-arch=sm_30 -m64\n"
        )
        self.assertEqual(build.host_cpu_flag_problems(config_mak, "aarch64"), [])
        self.assertTrue(build.host_cpu_flag_problems("CFLAGS=-O2 -mavx2\n", "aarch64"))
        self.assertTrue(build.host_cpu_flag_problems("CFLAGS=-march=native\n", "x86_64"))

    def test_pc_declares_system_library(self):
        texts = ["Libs.private: -lva-drm -lva -lm\n"]
        self.assertTrue(build.pc_declares(texts, "libva"))
        self.assertTrue(build.pc_declares(texts, "libva-drm"))
        self.assertFalse(build.pc_declares(["Libs.private: -lva-drm\n"], "libva"))

    def test_gnu_stack_size(self):
        headers = (
            "  Type           Offset   VirtAddr           PhysAddr           FileSiz  MemSiz   Flg Align\n"
            "  GNU_STACK      0x000000 0x0000000000000000 0x0000000000000000 0x000000 0x200000 RW  0x10\n"
        )
        self.assertEqual(build.gnu_stack_size(headers), 2 * 1024 * 1024)
        self.assertIsNone(build.gnu_stack_size("  LOAD 0x0 0x0 0x0 0x10 0x10 R 0x1000\n"))

    def test_parse_archive_name(self):
        parsed = build.parse_archive_name("ffmpeg-play-sdk-9.0.2-x86_64-unknown-linux-musl.tar.xz")
        self.assertEqual(
            parsed,
            {"profile": "play-sdk", "version": "9.0.2", "target": "x86_64-unknown-linux-musl"},
        )
        parsed = build.parse_archive_name("ffmpeg-tools-9.0.2-aarch64-apple-darwin.tar.xz")
        self.assertEqual(parsed["target"], "aarch64-apple-darwin")
        for name in (
            "ffmpeg-9.0.2+20261104-aarch64-apple-darwin-tools.tar.gz",
            "ffmpeg-tools-9.0.2-aarch64-apple-darwin.tar.gz",
            "ffmpeg-9.0.2-aarch64-apple-darwin.tar.xz",
        ):
            with self.assertRaises(SystemExit):
                build.parse_archive_name(name)

    def test_absolute_build_tree_marker(self):
        self.assertTrue(build.ABSOLUTE_BUILD_TREE.search(b"/home/runner/x/.work/build/a.c"))
        self.assertFalse(build.ABSOLUTE_BUILD_TREE.search(b"./.work/build/a.c"))


class StageTests(unittest.TestCase):
    def setUp(self):
        build.TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=build.TMP_ROOT)
        self.stage = pathlib.Path(self.temp.name) / "stage"

    def tearDown(self):
        self.temp.cleanup()

    def test_normalize_pc_removes_build_prefix(self):
        pc_dir = self.stage / "lib" / "pkgconfig"
        pc_dir.mkdir(parents=True)
        pc = pc_dir / "libavcodec.pc"
        pc.write_text(
            "prefix=/build/prefix\n"
            "exec_prefix=${prefix}\n"
            "libdir=${exec_prefix}/lib\n"
            "includedir=${prefix}/include\n"
            "\n"
            "Name: libavcodec\n"
            "Version: 1\n"
            "Libs: -L${libdir} -lavcodec\n"
            "Cflags: -I${includedir}\n"
        )
        build.normalize_pc(self.stage)
        text = pc.read_text()
        self.assertIn("prefix=${pcfiledir}/../..", text)
        self.assertNotIn("/build/prefix", text)
        self.assertIn("libdir=${prefix}/lib", text)

    def test_prune_stage_keeps_manifest(self):
        (self.stage / "share" / "man").mkdir(parents=True)
        (self.stage / "share" / "ffmpeg" / "examples").mkdir(parents=True)
        manifest = self.stage / "share" / "ffmpeg-build" / "manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"contract": 1}))
        build.prune_stage(self.stage, "sdk")
        self.assertFalse((self.stage / "share" / "man").exists())
        self.assertFalse((self.stage / "share" / "ffmpeg").exists())
        self.assertTrue(manifest.is_file())

    def test_prune_tools_stage_keeps_only_programs(self):
        for relative in ("bin/ffmpeg", "bin/ffprobe", "lib/libavcodec.a", "include/libavutil/avutil.h"):
            path = self.stage / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        build.prune_stage(self.stage, "tools")
        self.assertTrue((self.stage / "bin" / "ffmpeg").is_file())
        self.assertTrue((self.stage / "bin" / "ffprobe").is_file())
        self.assertFalse((self.stage / "lib").exists())
        self.assertFalse((self.stage / "include").exists())

    def test_build_prefix_leaks(self):
        clean = self.stage / "lib" / "clean.a"
        dirty = self.stage / "lib" / "dirty.a"
        clean.parent.mkdir(parents=True)
        clean.write_bytes(b"./libavutil/log.c")
        dirty.write_bytes(str(build.ROOT).encode() + b"/.work/build/x.c")
        self.assertEqual(build.build_prefix_leaks(self.stage), ["lib/dirty.a"])

    def write_package_stage(self, target: str, commit: str, profile_name: str = "tools") -> pathlib.Path:
        profile, _ = build.load_profile(profile_name)
        lock = build.load_sources()
        stage = self.stage / target / profile_name
        manifest = {
            "profile": profile_name,
            "target": target,
            "sources": {
                name: {"version": lock[name].version, "url": lock[name].url, "sha256": lock[name].sha256}
                for name in profile["sources"]
            },
            "producer": {"commit": commit},
        }
        paths = [*build.notice_paths(profile), *(f"bin/{name}" for name in build.TOOLS_PROGRAMS)]
        if profile_name == "runtime":
            paths.append("include/libavutil/ffversion.h")
            for library in build.RUNTIME_LIBRARIES:
                paths.extend((f"lib/{library}.dylib", f"lib/pkgconfig/{library}.pc"))
        for relative in paths:
            path = stage / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        path = stage / "share" / "ffmpeg-build" / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest))
        return path

    def test_corrupt_build_stamp_defers_rebuild_until_sources_are_available(self):
        target = "aarch64-apple-darwin"
        manifest = self.write_package_stage(target, "e" * 40)
        build_root = pathlib.Path(self.temp.name) / "build"
        build_dir = build_root / target / "tools"
        build_dir.mkdir(parents=True)
        stamp = build_dir / "stamp.json"
        toolchain = {"compiler": "fixture"}
        arguments = ["--disable-network"]
        _, profile_path = build.load_profile("tools")
        fingerprint = build.build_fingerprint(profile_path, target, "tools", arguments, toolchain)
        original = manifest.read_bytes()

        with (
            mock.patch.object(build, "BUILD_ROOT", build_root),
            mock.patch.object(build, "STAGE_ROOT", self.stage),
            mock.patch.object(build, "require_native_host"),
            mock.patch.object(build, "platform_toolchain", return_value=toolchain),
            mock.patch.object(build, "configure_args_for", return_value=arguments),
            mock.patch.object(build, "fetch_profile_sources", side_effect=RuntimeError("source unavailable")) as fetch,
            redirect_stdout(io.StringIO()) as stdout,
        ):
            stamp.write_text(json.dumps({"fingerprint": fingerprint}))
            build.build(target, "tools")
            self.assertIn("up to date:", stdout.getvalue())
            fetch.assert_not_called()

            for content in (b"[]", b"{", bytes([255])):
                with self.subTest(content=content):
                    fetch.reset_mock()
                    stamp.write_bytes(content)
                    with self.assertRaisesRegex(RuntimeError, "^source unavailable$"):
                        build.build(target, "tools")
                    fetch.assert_called_once()
                    self.assertEqual(manifest.read_bytes(), original)
                    self.assertEqual(stamp.read_bytes(), content)

    def test_package_writes_archive_and_release_manifest(self):
        commit = "e" * 40
        target = "aarch64-apple-darwin"
        self.write_package_stage(target, commit)
        dist = pathlib.Path(self.temp.name) / "dist"
        stdout = io.StringIO()
        with (
            mock.patch.object(build, "DIST", dist),
            mock.patch.object(build, "STAGE_ROOT", self.stage),
            redirect_stdout(stdout),
        ):
            archive = build.package(target, "tools")
        version = build.load_sources()["ffmpeg"].version
        self.assertEqual(archive.name, f"ffmpeg-tools-{version}-{target}.tar.xz")
        self.assertEqual(stdout.getvalue().splitlines()[-1], f"{hashing.sha256_file(archive)}  {archive.name}")
        sidecar = json.loads((dist / f"ffmpeg-tools-{version}-{target}.manifest.json").read_text())
        self.assertEqual(
            sidecar,
            {
                "schema_version": 1,
                "product": "ffmpeg-tools",
                "version": version,
                "target": target,
                "source_revision": commit,
                "sources_lock_sha256": hashing.sha256_file(build.ROOT / "sources.lock.json"),
            },
        )
        with build.tarfile.open(archive, "r:xz") as opened:
            names = opened.getnames()
            self.assertTrue(all(member.mtime == 0 for member in opened.getmembers()))
            handle = opened.extractfile(f"ffmpeg-tools-{version}-{target}/share/ffmpeg-build/manifest.json")
            assert handle is not None
            inner = json.load(handle)
        self.assertIn(f"ffmpeg-tools-{version}-{target}/bin/ffmpeg", names)
        self.assertEqual(inner["release"], {"archive": archive.name})

    def test_missing_source_inventory_requires_all_profile_pins(self):
        profile, _ = build.load_profile("tools")
        self.assertEqual(build.mismatched_source_pins({}, profile, build.load_sources()), ["ffmpeg", "dav1d", "zlib"])

    def test_package_reports_incomplete_stage(self):
        target = "aarch64-apple-darwin"
        stage = self.stage / target / "tools"
        with (
            mock.patch.object(build, "STAGE_ROOT", self.stage),
            self.assertRaises(SystemExit) as error,
        ):
            build.package(target, "tools")
        self.assertEqual(str(error.exception), f"error: stage {stage} is incomplete; run build first")

    def test_package_rejects_invalid_stage_identity_without_writing(self):
        target = "aarch64-apple-darwin"
        path = self.write_package_stage(target, "e" * 40)
        valid = json.loads(path.read_text())
        stale = json.loads(path.read_text())
        stale["sources"]["dav1d"]["sha256"] = "0" * 64
        del stale["sources"]["zlib"]
        cases = (
            (valid | {"profile": "runtime"}, f"stage manifest is for runtime/{target}"),
            (valid | {"target": "x86_64-unknown-linux-musl"}, "stage manifest is for tools/x86_64-unknown-linux-musl"),
            ({key: value for key, value in valid.items() if key != "sources"},
             "stage manifest FFmpeg version disagrees with sources.lock.json"),
            (valid | {"sources": {}}, "stage manifest FFmpeg version disagrees with sources.lock.json"),
            ({key: value for key, value in valid.items() if key != "producer"},
             "stage manifest producer commit is not a commit hash"),
            (valid | {"producer": {}}, "stage manifest producer commit is not a commit hash"),
            (stale, "stage manifest sources disagree with sources.lock.json: dav1d, zlib"),
        )
        dist = pathlib.Path(self.temp.name) / "dist"
        with mock.patch.object(build, "DIST", dist), mock.patch.object(build, "STAGE_ROOT", self.stage):
            for manifest, message in cases:
                with self.subTest(message=message):
                    original = json.dumps(manifest)
                    path.write_text(original)
                    with self.assertRaises(SystemExit) as error:
                        build.package(target, "tools")
                    self.assertEqual(str(error.exception), f"error: {message}")
                    self.assertEqual(path.read_text(), original)
                    self.assertFalse(dist.exists())

    def test_manifest_reader_reports_present_and_missing_stage_files(self):
        target = "aarch64-apple-darwin"
        stage = self.stage / target / "tools"
        expected = stage / "share" / "ffmpeg-build" / "manifest.json"
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            check = build.Audit()
            self.assertEqual(build.read_manifest(check, stage), {})
            self.assertEqual(check.finish(), 1)
        self.assertEqual(stdout.getvalue().splitlines(), [
            f"FAIL audit: manifest readable: missing {expected}", "TOTAL 0 passed, 1 failed",
        ])

        self.assertEqual(self.write_package_stage(target, "e" * 40), expected)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            check = build.Audit()
            self.assertEqual(build.read_manifest(check, stage), json.loads(expected.read_text()))
            self.assertEqual(check.finish(), 0)
        self.assertEqual(stdout.getvalue().splitlines(), ["PASS audit: manifest readable", "TOTAL 1 passed, 0 failed"])

    def test_stage_manifest_rejects_malformed_records_before_writing(self):
        target = "aarch64-apple-darwin"
        path = self.write_package_stage(target, "e" * 40)
        dist = pathlib.Path(self.temp.name) / "dist"
        valid = json.loads(path.read_text())
        cases = (
            ("[]", "manifest root must be an object"),
            ("{", "Expecting property name"),
            (json.dumps(valid | {"sources": []}), "manifest sources must be an object"),
            (json.dumps(valid | {"sources": {"ffmpeg": None}}), "manifest source ffmpeg must be an object"),
            (json.dumps(valid | {"producer": []}), "manifest producer must be an object"),
            (json.dumps(valid | {"producer": {"commit": 12}}), "manifest producer.commit must be a string"),
            (json.dumps(valid | {"toolchain": []}), "manifest toolchain must be an object"),
            (json.dumps(valid | {"toolchain": {"libc": None}}), "manifest toolchain.libc must be a string"),
            (json.dumps(valid | {"toolchain": {"cc": 12}}), "manifest toolchain.cc must be a string"),
            (json.dumps(valid | {"toolchain": {"sysroot": []}}), "manifest toolchain.sysroot must be a string"),
            (json.dumps(valid | {"toolchain": {"cpu_baseline": True}}), "manifest toolchain.cpu_baseline must be a string"),
        )
        with mock.patch.object(build, "DIST", dist), mock.patch.object(build, "STAGE_ROOT", self.stage):
            for contents, message in cases:
                with self.subTest(contents=contents):
                    path.write_text(contents)
                    stdout = io.StringIO()
                    check = build.Audit()
                    with redirect_stdout(stdout):
                        self.assertEqual(build.read_manifest(check, path.parents[2]), {})
                        self.assertEqual(check.finish(), 1)
                    self.assertIn(f"FAIL audit: manifest readable: {message}", stdout.getvalue())
                    with self.assertRaisesRegex(SystemExit, f"stage manifest is unreadable: {message}"):
                        build.package(target, "tools")
                    self.assertEqual(path.read_text(), contents)
                    self.assertFalse(dist.exists())

    def test_audit_requires_native_host_build_tree_and_stage(self):
        target = "aarch64-apple-darwin"
        build_root = pathlib.Path(self.temp.name) / "build"
        with (
            mock.patch.object(build, "STAGE_ROOT", self.stage),
            mock.patch.object(build, "BUILD_ROOT", build_root),
            mock.patch.object(build.targets, "native_target") as native_target,
        ):
            native_target.return_value = build.targets.target_for_triple("aarch64-unknown-linux-musl")
            with self.assertRaisesRegex(SystemExit, f"target {target} builds natively"):
                build.audit(target, "tools")

            native_target.return_value = build.targets.target_for_triple(target)
            stage, build_dir, _ = build.build_paths("tools", target)
            with self.assertRaises(SystemExit) as error:
                build.audit(target, "tools")
            self.assertEqual(str(error.exception), f"error: missing build tree {build_dir}; run build first")

            build_dir.mkdir(parents=True)
            with self.assertRaises(SystemExit) as error:
                build.audit(target, "tools")
            self.assertEqual(str(error.exception), f"error: missing stage {stage}; run build first")

            stage.mkdir(parents=True)
            with self.assertRaises(SystemExit) as error:
                build.audit(target, "tools")
            self.assertEqual(str(error.exception), f"error: missing {build_dir / 'ffmpeg' / 'config_components.h'}")

    def test_audit_reports_inconsistent_build_tree_and_stage(self):
        target = "aarch64-unknown-linux-musl"
        profile, path = build.load_profile("tools")
        profile = profile | {"components": {"protocols": ["file"], "indevs": ["lavfi"], "encoders": ["aac"]}}
        config = build.target_config(profile, target)
        toolchain = {"cc": "fixture clang", "sysroot": "/", "cpu_baseline": config["cpu_baseline"], "libc": "musl 1.2.6"}
        build_root = pathlib.Path(self.temp.name) / "build"
        ffmpeg = build_root / target / "tools" / "ffmpeg"
        config_mak = ffmpeg / "ffbuild" / "config.mak"
        config_mak.parent.mkdir(parents=True)
        components = ffmpeg / "config_components.h"
        good_components = "#define CONFIG_FILE_PROTOCOL 1\n#define CONFIG_LAVFI_INDEV 1\n#define CONFIG_AAC_ENCODER 1\n"
        (ffmpeg / "config.h").write_text("#define ARCH_AARCH64 1\n")
        effective_config = "--disable-network --enable-avdevice"
        good_config = (
            f"FFMPEG_CONFIGURATION={effective_config}\nCONFIG_ZLIB=yes\nCONFIG_GPL=yes\n"
            f"CFLAGS=-fPIC -march={config['cpu_baseline']}\n"
        )
        with (
            mock.patch.object(build, "load_profile", return_value=(profile, path)),
            mock.patch.object(build, "STAGE_ROOT", self.stage),
            mock.patch.object(build, "BUILD_ROOT", build_root),
            mock.patch.object(build, "require_native_host"),
            mock.patch.object(build, "platform_toolchain", return_value=toolchain),
            mock.patch.object(build, "audit_tools") as audit_programs,
        ):
            manifest_file = self.write_package_stage(target, "e" * 40)
            stage, build_dir, deps = build.build_paths("tools", target)
            valid = json.loads(manifest_file.read_text()) | {
                "contract": 1,
                "components": {"protocols": ["file"], "indevs": ["lavfi"], "encoders": ["aac"]},
                "auto_selected": {},
                "external_libraries": [],
                "bundled_dependencies": config.get("bundled_dependencies", []),
                "frameworks": config.get("frameworks", []),
                "system_libraries": config.get("system_libraries", []),
                "toolchain": toolchain,
                "configure_args": build.configure_args_for(profile, target, build_dir, deps, toolchain),
                "configure": effective_config,
                "license": "GPL version 2 or later",
            }
            wrong_commit = valid | {"producer": {"commit": "local"}}
            cases = (
                (valid, good_config, good_components, []),
                (wrong_commit, good_config, good_components, ["manifest producer commit"]),
                (valid | {"toolchain": []}, good_config, good_components, ["manifest readable"]),
                (valid | {"toolchain": toolchain | {"libc": None}}, good_config, good_components, ["manifest readable"]),
                (valid | {"contract": 2}, good_config, good_components, ["manifest contract"]),
                (valid | {"profile": "runtime"}, good_config, good_components, ["manifest profile and target"]),
                (valid | {"target": "x86_64-unknown-linux-musl"}, good_config, good_components,
                 ["manifest profile and target"]),
                (valid | {"sources": valid["sources"] | {"ffmpeg": {"sha256": "0" * 64}}},
                 good_config, good_components, ["manifest sources"]),
                (valid, good_config.replace("--disable-network ", ""), good_components,
                 ["network disabled in configure", "manifest effective configure"]),
                (valid, good_config.replace(" -march=", " -flto -march="), good_components, ["no LTO flags"]),
                (valid, good_config.replace("CONFIG_ZLIB=yes", "CONFIG_ZLIB=no"), good_components, ["zlib enabled"]),
                (valid, good_config.replace("CFLAGS=-fPIC ", "CFLAGS="), good_components, ["PIC enabled"]),
                (valid, good_config.replace("CONFIG_GPL=yes", "CONFIG_GPL=no"), good_components,
                 ["FFmpeg license flags match gpl"]),
                (valid | {"configure": "--disable-network"}, good_config.replace(" --enable-avdevice", ""),
                 good_components, ["libavdevice only for requested input devices"]),
                (valid | {"external_libraries": ["vorbis"]}, good_config + "CONFIG_LIBVORBIS=yes\n", good_components,
                 ["external libraries allowed"]),
                (valid | {"components": valid["components"] | {"outdevs": ["null"]},
                          "auto_selected": {"outdevs": ["null"]}},
                 good_config, good_components + "#define CONFIG_NULL_OUTDEV 1\n", ["no devices or output devices"]),
                (valid, good_config, good_components.replace("CONFIG_AAC_ENCODER", "CONFIG_MP3_ENCODER"),
                 ["no unrequested encoders", "requested encoders present", "manifest components match build tree",
                  "manifest auto-selected match build tree"]),
            )
            manifest_mismatches = (
                ("components", {}, "manifest components match build tree"),
                ("auto_selected", {"encoders": ["aac"]}, "manifest auto-selected match build tree"),
                ("external_libraries", ["dav1d"], "manifest external libraries"),
                ("bundled_dependencies", [], "manifest bundled dependencies"),
                ("frameworks", ["CoreMedia"], "manifest frameworks"),
                ("system_libraries", ["libva"], "manifest system libraries"),
                ("configure_args", [], "manifest configure arguments"),
                ("configure", "--disable-network", "manifest effective configure"),
                ("license", "LGPL version 2.1 or later", "manifest license is GPL version 2 or later"),
                ("toolchain", toolchain | {"cc": ""}, "manifest toolchain"),
                ("toolchain", toolchain | {"sysroot": ""}, "manifest toolchain"),
                ("toolchain", toolchain | {"cpu_baseline": ""}, "manifest toolchain"),
                ("toolchain", toolchain | {"libc": "glibc"}, "manifest libc is musl"),
            )
            cases += tuple(
                (valid | {field: value}, good_config, good_components, [failure])
                for field, value, failure in manifest_mismatches
            )
            for manifest, config_text, component_text, failures in cases:
                with self.subTest(failures=failures), redirect_stdout(io.StringIO()) as stdout:
                    manifest_file.write_text(json.dumps(manifest))
                    config_mak.write_text(config_text)
                    components.write_text(component_text)
                    self.assertEqual(build.audit(target, "tools"), int(bool(failures)), stdout.getvalue())
                    result = [line.partition(": ")[2].split(": ", 1)[0] for line in stdout.getvalue().splitlines()
                              if line.startswith("FAIL audit: ")]
                    self.assertEqual(result, failures)
                    self.assertEqual(audit_programs.call_args.args[1:],
                                     (config, stage, build.load_sources()["ffmpeg"].version))

    def test_audit_runtime_checks_shared_configuration_and_dispatches_to_runtime(self):
        target = "aarch64-unknown-linux-musl"
        profile, profile_path = build.load_profile("runtime")
        profile = profile | {"components": {"protocols": ["file"]}}
        config = build.target_config(profile, target)
        toolchain = {"cc": "fixture clang", "sysroot": "/", "cpu_baseline": config["cpu_baseline"], "libc": "musl 1.2.6"}
        build_root = pathlib.Path(self.temp.name) / "build"
        with (
            mock.patch.object(build, "load_profile", return_value=(profile, profile_path)),
            mock.patch.object(build, "STAGE_ROOT", self.stage),
            mock.patch.object(build, "BUILD_ROOT", build_root),
            mock.patch.object(build, "require_native_host"),
            mock.patch.object(build, "platform_toolchain", return_value=toolchain),
            mock.patch.object(build, "audit_runtime") as audit_runtime,
        ):
            stage, build_dir, deps = build.build_paths("runtime", target)
            ffmpeg = build_dir / "ffmpeg"
            config_mak = ffmpeg / "ffbuild" / "config.mak"
            config_mak.parent.mkdir(parents=True)
            (ffmpeg / "config.h").write_text("#define ARCH_AARCH64 1\n")
            (ffmpeg / "config_components.h").write_text(
                "#define CONFIG_FILE_PROTOCOL 1\n"
                "#define CONFIG_AV1_DECODER 1\n"
                "#define CONFIG_AV1_VAAPI_HWACCEL 1\n"
                "#define CONFIG_H264_VAAPI_HWACCEL 1\n"
                "#define CONFIG_HEVC_VAAPI_HWACCEL 1\n"
                "#define CONFIG_VP9_VAAPI_HWACCEL 1\n"
            )
            components = {
                "protocols": ["file"],
                "decoders": ["av1"],
                "hwaccels": ["av1_vaapi", "h264_vaapi", "hevc_vaapi", "vp9_vaapi"],
            }
            requested = components | {"hwaccels": ["h264_vaapi", "hevc_vaapi", "vp9_vaapi", "av1_vaapi"]}
            configuration = "--disable-network"
            config_text = (
                f"FFMPEG_CONFIGURATION={configuration}\nCONFIG_ZLIB=yes\nCONFIG_GPL=yes\n"
                f"CFLAGS=-fPIC -march={config['cpu_baseline']}\n"
            )
            manifest_file = self.write_package_stage(target, "e" * 40, "runtime")
            manifest = json.loads(manifest_file.read_text()) | {
                "contract": 1,
                "components": components,
                "auto_selected": {},
                "external_libraries": [],
                "bundled_dependencies": config.get("bundled_dependencies", []),
                "frameworks": config.get("frameworks", []),
                "system_libraries": config.get("system_libraries", []),
                "toolchain": toolchain,
                "configure_args": build.configure_args_for(profile, target, build_dir, deps, toolchain),
                "configure": configuration,
                "license": "GPL version 2 or later",
            }
            manifest_file.write_text(json.dumps(manifest))
            for flags, expected in (("CONFIG_SHARED=yes\n", 0), ("", 1), ("CONFIG_SHARED=yes\nCONFIG_STATIC=yes\n", 1)):
                with self.subTest(flags=flags), redirect_stdout(io.StringIO()) as stdout:
                    audit_runtime.reset_mock()
                    config_mak.write_text(config_text + flags)
                    self.assertEqual(build.audit(target, "runtime"), expected, stdout.getvalue())
                    self.assertEqual(
                        [line for line in stdout.getvalue().splitlines() if line.startswith("FAIL audit: ")],
                        ["FAIL audit: shared libraries only"] if expected else [],
                    )
                    audit_runtime.assert_called_once()
                    self.assertEqual(
                        audit_runtime.call_args.args[1:],
                        (config, stage, build.load_sources()["ffmpeg"].version, requested, components, manifest),
                    )

    def test_audit_sdk_rejects_effective_encoders_and_muxers(self):
        target = "aarch64-apple-darwin"
        profile, profile_path = build.load_profile("play-sdk")
        profile = profile | {"components": {"protocols": ["file"]}}
        config = build.target_config(profile, target)
        toolchain = {"cc": "fixture clang", "sysroot": "/", "cpu_baseline": config["cpu_baseline"]}
        build_root = pathlib.Path(self.temp.name) / "build"
        with (
            mock.patch.object(build, "load_profile", return_value=(profile, profile_path)),
            mock.patch.object(build, "STAGE_ROOT", self.stage),
            mock.patch.object(build, "BUILD_ROOT", build_root),
            mock.patch.object(build, "require_native_host"),
            mock.patch.object(build, "platform_toolchain", return_value=toolchain),
            mock.patch.object(build, "audit_sdk") as audit_sdk,
        ):
            stage, build_dir, deps = build.build_paths("play-sdk", target)
            ffmpeg = build_dir / "ffmpeg"
            config_mak = ffmpeg / "ffbuild" / "config.mak"
            config_mak.parent.mkdir(parents=True)
            configuration = "--disable-network"
            config_mak.write_text(f"FFMPEG_CONFIGURATION={configuration}\nCONFIG_ZLIB=yes\nCFLAGS=-fPIC\n")
            header = (
                "#define CONFIG_FILE_PROTOCOL 1\n"
                "#define CONFIG_H264_VIDEOTOOLBOX_HWACCEL 1\n"
                "#define CONFIG_HEVC_VIDEOTOOLBOX_HWACCEL 1\n"
            )
            components = {"protocols": ["file"], "hwaccels": ["h264_videotoolbox", "hevc_videotoolbox"]}
            manifest_file = self.write_package_stage(target, "e" * 40, "play-sdk")
            manifest = json.loads(manifest_file.read_text()) | {
                "contract": 1,
                "external_libraries": [],
                "bundled_dependencies": config.get("bundled_dependencies", []),
                "frameworks": config.get("frameworks", []),
                "system_libraries": config.get("system_libraries", []),
                "toolchain": toolchain,
                "configure_args": build.configure_args_for(profile, target, build_dir, deps, toolchain),
                "configure": configuration,
                "license": "LGPL version 2.1 or later",
            }
            cases = (
                ("", {}, []),
                ("#define CONFIG_AAC_ENCODER 1\n", {"encoders": ["aac"]}, ["no encoders"]),
                ("#define CONFIG_MP4_MUXER 1\n", {"muxers": ["mp4"]}, ["no muxers"]),
            )
            for extra_header, extra_components, failures in cases:
                with self.subTest(extra_components=extra_components), redirect_stdout(io.StringIO()) as stdout:
                    audit_sdk.reset_mock()
                    (ffmpeg / "config_components.h").write_text(header + extra_header)
                    manifest_file.write_text(json.dumps(manifest | {
                        "components": components | extra_components,
                        "auto_selected": extra_components,
                    }))
                    self.assertEqual(build.audit(target, "play-sdk"), int(bool(failures)), stdout.getvalue())
                    self.assertEqual(
                        [line.partition(": ")[2].split(": ", 1)[0] for line in stdout.getvalue().splitlines()
                         if line.startswith("FAIL audit: ")],
                        failures,
                    )
                    audit_sdk.assert_called_once()
                    self.assertEqual(
                        audit_sdk.call_args.args[1:],
                        (target, "play-sdk", config, stage, build.load_sources()["ffmpeg"].version),
                    )

    def test_package_reports_archive_error_for_a_symlinked_stage(self):
        target = "aarch64-apple-darwin"
        stage = self.write_package_stage(target, "e" * 40).parents[2]
        actual_stage = stage.with_name("previous-stage")
        stage.rename(actual_stage)
        stage.symlink_to(actual_stage, target_is_directory=True)
        dist = pathlib.Path(self.temp.name) / "dist"
        with (
            mock.patch.object(build, "DIST", dist),
            mock.patch.object(build, "STAGE_ROOT", self.stage),
            self.assertRaises(SystemExit) as error,
        ):
            build.package(target, "tools")
        self.assertEqual(str(error.exception), f"error: archive source is not a directory: {stage}")
        self.assertFalse(dist.exists())

    def test_only_runtime_packages_preserve_internal_symlinks(self):
        target = "aarch64-apple-darwin"
        commit = "e" * 40
        dist = pathlib.Path(self.temp.name) / "dist"
        self.write_package_stage(target, commit)
        tools_lib = self.stage / target / "tools" / "lib"
        tools_lib.mkdir()
        (tools_lib / "payload").write_bytes(b"fixture")
        (tools_lib / "alias").symlink_to("payload")
        with mock.patch.object(build, "DIST", dist), mock.patch.object(build, "STAGE_ROOT", self.stage):
            with self.assertRaises(SystemExit) as error:
                build.package(target, "tools")
            self.assertEqual(str(error.exception), "error: tools stages carry no symlinks; found ['lib/alias']")
            self.assertFalse(dist.exists())

            self.write_package_stage(target, commit, "runtime")
            library = self.stage / target / "runtime" / "lib" / "libavutil.dylib"
            library.rename(library.with_name("libavutil.1.dylib"))
            library.symlink_to("libavutil.1.dylib")
            archive = build.package(target, "runtime")
        with build.tarfile.open(archive, "r:xz") as opened:
            member = opened.getmember(f"{archive.name.removesuffix('.tar.xz')}/lib/libavutil.dylib")
            self.assertTrue(member.issym())
            self.assertEqual(member.linkname, "libavutil.1.dylib")

    def qualification_fixture(self, target, profile_name):
        manifest_path = self.write_package_stage(target, "e" * 40, profile_name)
        version = build.load_sources()["ffmpeg"].version
        name = f"ffmpeg-{profile_name}-{version}-{target}"
        archive = pathlib.Path(self.temp.name) / f"{name}.tar.xz"
        manifest = json.loads(manifest_path.read_text())
        manifest.update({
            "contract": 1, "configure_args": [], "components": {}, "auto_selected": {},
            "external_libraries": [], "bundled_dependencies": [], "frameworks": [],
            "system_libraries": [], "toolchain": {}, "license": "gpl",
        })
        manifest["release"] = {"archive": archive.name}
        return archive, manifest_path, manifest

    def test_qualify_checks_artifact_manifest_and_propagates_script_status(self):
        target = "aarch64-apple-darwin"
        archive, manifest_path, manifest = self.qualification_fixture(target, "tools")
        stage = manifest_path.parents[2]
        name = archive.name.removesuffix(".tar.xz")
        manifest_path.write_text(json.dumps(manifest))
        work = pathlib.Path(self.temp.name) / "qualification"

        with (
            mock.patch.object(build, "TMP_ROOT", work),
            mock.patch.object(build, "require_native_host") as native_host,
            mock.patch.object(build.tarfile.TarFile, "extraction_filter", staticmethod(lambda *_: None)),
            mock.patch.object(build.subprocess, "run", return_value=mock.Mock(returncode=0)) as runner,
        ):
            build.release.create_archive(stage, archive, mtime=0, prefix=name)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(build.qualify(archive), 0)
            self.assertIn("PASS audit: qualify-tools.sh passes", stdout.getvalue())
            profile, _ = build.load_profile("tools")
            native_host.assert_called_once_with(build.target_config(profile, target), target)
            runner.assert_called_once_with(
                ["bash", str(build.ROOT / "tests" / "qualify-tools.sh"),
                 str(work / "qualify" / name / "path with spaces" / name), target],
                check=False,
            )
            runner.return_value.returncode = 1
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(build.qualify(archive), 1)
            self.assertIn("FAIL audit: qualify-tools.sh passes", stdout.getvalue())

            runner.return_value.returncode = 0
            manifest["sources"]["dav1d"]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest))
            build.release.create_archive(stage, archive, mtime=0, prefix=name)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(build.qualify(archive), 1)
            self.assertIn("FAIL audit: manifest sources match the lock", stdout.getvalue())

            manifest_path.write_text("{")
            build.release.create_archive(stage, archive, mtime=0, prefix=name)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(build.qualify(archive), 1)
            self.assertIn("FAIL audit: manifest readable", stdout.getvalue())

            runner.reset_mock()
            build.release.create_archive(stage, archive, mtime=1, prefix=name)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(build.qualify(archive), 1)
            report = stdout.getvalue().splitlines()[0]
            self.assertTrue(report.startswith("FAIL audit: archive members are normalized and under the root: "))
            with build.tarfile.open(archive, "r:xz") as opened:
                examples = opened.getnames()[:5]
            self.assertEqual(report.split(": ", 2)[2].split("; "), [
                f"non-normalized owner or mtime: {member}" for member in examples
            ])
            runner.assert_not_called()
            self.assertFalse((work / "qualify" / name / "path with spaces" / name).exists())

    def test_qualify_reports_missing_notices_and_bounded_prefix_leaks(self):
        target = "aarch64-apple-darwin"
        archive, manifest_path, manifest = self.qualification_fixture(target, "tools")
        stage = manifest_path.parents[2]
        name = archive.name.removesuffix(".tar.xz")
        work = pathlib.Path(self.temp.name) / "qualification"
        manifest_path.write_text(json.dumps(manifest))
        (stage / "README").unlink()
        leaks = [f"leaked-{index:02}.txt" for index in range(11)]
        for relative in leaks:
            (stage / relative).write_text("fixture from /example/.work/build/ffmpeg")
        build.release.create_archive(stage, archive, mtime=0, prefix=name)
        stdout = io.StringIO()
        with (
            mock.patch.object(build, "TMP_ROOT", work),
            mock.patch.object(build, "require_native_host"),
            mock.patch.object(build.subprocess, "run", return_value=mock.Mock(returncode=0)),
            redirect_stdout(stdout),
        ):
            self.assertEqual(build.qualify(archive), 1)
        lines = stdout.getvalue().splitlines()
        self.assertIn(f"PASS audit: archive root is {name}", lines)
        self.assertIn("FAIL audit: README and licenses present: missing: ['README']", lines)
        self.assertIn(f"FAIL audit: no absolute build-tree path in any file: files: {leaks[:10]}", lines)

    def test_qualify_requires_xz_content(self):
        target = "aarch64-apple-darwin"
        archive, manifest_path, manifest = self.qualification_fixture(target, "tools")
        manifest_path.write_text(json.dumps(manifest))
        name = archive.name.removesuffix(".tar.xz")
        with build.tarfile.open(archive, "w") as uncompressed:
            uncompressed.add(manifest_path.parents[2], arcname=name)
        work = pathlib.Path(self.temp.name) / "qualification"
        with (
            mock.patch.object(build, "TMP_ROOT", work),
            mock.patch.object(build, "require_native_host"),
            self.assertRaises(build.tarfile.ReadError),
        ):
            build.qualify(archive)

    def test_qualify_rejects_conflicting_manifest_identity(self):
        target = "aarch64-apple-darwin"
        archive, manifest_path, valid = self.qualification_fixture(target, "tools")
        stage = manifest_path.parents[2]
        name = archive.name.removesuffix(".tar.xz")
        work = pathlib.Path(self.temp.name) / "qualification"
        cases = (
            ("profile", "runtime", "manifest profile matches name"),
            ("target", "x86_64-unknown-linux-musl", "manifest target matches name"),
            ("sources", valid["sources"] | {"ffmpeg": valid["sources"]["ffmpeg"] | {"version": "0.0.0"}},
             "manifest FFmpeg version matches name"),
            ("producer", {"commit": "missing"}, "manifest producer commit is a commit hash"),
            ("release", {"archive": "old.tar.xz"}, "manifest release matches name"),
        )
        with (
            mock.patch.object(build, "TMP_ROOT", work),
            mock.patch.object(build, "require_native_host"),
            mock.patch.object(build.subprocess, "run", return_value=mock.Mock(returncode=0)),
        ):
            for key, value, diagnostic in cases:
                with self.subTest(field=key):
                    manifest_path.write_text(json.dumps(valid | {key: value}))
                    build.release.create_archive(stage, archive, mtime=0, prefix=name)
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        self.assertEqual(build.qualify(archive), 1)
                    self.assertIn(f"FAIL audit: {diagnostic}", stdout.getvalue())

            manifest_path.write_text(json.dumps({key: value for key, value in valid.items() if key != "toolchain"}))
            build.release.create_archive(stage, archive, mtime=0, prefix=name)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(build.qualify(archive), 1)
            self.assertIn("FAIL audit: manifest has the contract keys: missing: ['toolchain']", stdout.getvalue())

    def test_qualify_runtime_checks_extracted_library_bytes_and_links(self):
        for target, suffix, identity in (
            ("aarch64-apple-darwin", "dylib", "install_name"),
            ("x86_64-unknown-linux-musl", "so", "soname"),
        ):
            with self.subTest(target=target):
                self.check_runtime_qualification(target, suffix, identity)

    def check_runtime_qualification(self, target, suffix, identity):
        archive, manifest_path, manifest = self.qualification_fixture(target, "runtime")
        stage = manifest_path.parents[2]
        libraries = {}
        for library in build.RUNTIME_LIBRARIES:
            file = f"lib/{library}.1.{suffix}"
            link = f"lib/{library}.{suffix}"
            (stage / f"lib/{library}.dylib").rename(stage / file)
            (stage / link).symlink_to(pathlib.Path(file).name)
            libraries[library] = {
                "file": file, "links": [link], identity: pathlib.Path(file).name,
                "sha256": hashing.sha256_file(stage / file),
            }
        manifest["libraries"] = libraries
        manifest_path.write_text(json.dumps(manifest))
        name = archive.name.removesuffix(".tar.xz")
        work = pathlib.Path(self.temp.name) / "qualification"
        with (
            mock.patch.object(build, "TMP_ROOT", work),
            mock.patch.object(build, "require_native_host"),
            mock.patch.object(build.subprocess, "run", return_value=mock.Mock(returncode=0)) as runner,
        ):
            build.release.create_archive(stage, archive, mtime=0, prefix=name)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(build.qualify(archive), 0)
            command = runner.call_args.args[0]
            self.assertEqual(pathlib.Path(command[1]).name, "qualify-runtime.sh")

            avutil_entry = libraries["libavutil"]
            malformed = (
                ([], "manifest libraries must be an object"),
                (libraries | {"libavutil": None}, "manifest libraries.libavutil must be an object"),
                (libraries | {"libavutil": avutil_entry | {"file": []}},
                 "manifest libraries.libavutil.file must be a string"),
                (libraries | {"libavutil": avutil_entry | {"links": "lib/alias"}},
                 "manifest libraries.libavutil.links must be a list of strings"),
                (libraries | {"libavutil": avutil_entry | {"links": [1]}},
                 "manifest libraries.libavutil.links must be a list of strings"),
            )
            for bad_libraries, diagnostic in malformed:
                with self.subTest(diagnostic=diagnostic):
                    manifest_path.write_text(json.dumps(manifest | {"libraries": bad_libraries}))
                    build.release.create_archive(stage, archive, mtime=0, prefix=name)
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        self.assertEqual(build.qualify(archive), 1)
                    self.assertIn(f"FAIL audit: manifest readable: {diagnostic}", stdout.getvalue().splitlines())

            manifest_path.write_text(json.dumps(manifest))
            avutil = stage / f"lib/libavutil.1.{suffix}"
            avutil.write_bytes(b"changed binary")
            build.release.create_archive(stage, archive, mtime=0, prefix=name)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(build.qualify(archive), 1)
            self.assertIn("libavutil: sha256 mismatch", stdout.getvalue())

            avutil.write_bytes(b"fixture")
            link = stage / f"lib/libavutil.{suffix}"
            link.unlink()
            link.symlink_to(f"libavcodec.1.{suffix}")
            build.release.create_archive(stage, archive, mtime=0, prefix=name)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(build.qualify(archive), 1)
            self.assertIn(
                f"FAIL audit: manifest libraries match the extracted files and links: "
                f"libavutil: lib/libavutil.{suffix} does not resolve to lib/libavutil.1.{suffix}",
                stdout.getvalue().splitlines(),
            )

            manifest_path.write_text(json.dumps({key: value for key, value in manifest.items() if key != "libraries"}))
            build.release.create_archive(stage, archive, mtime=0, prefix=name)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(build.qualify(archive), 1)
            self.assertIn("FAIL audit: manifest has the contract keys: missing: ['libraries']", stdout.getvalue())

            manifest_path.write_text(json.dumps(manifest))
            for library in build.RUNTIME_LIBRARIES:
                (stage / f"lib/{library}.1.{suffix}").write_bytes(b"changed binary")
            build.release.create_archive(stage, archive, mtime=0, prefix=name)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(build.qualify(archive), 1)
            first_five = "; ".join(f"{library}: sha256 mismatch" for library in sorted(build.RUNTIME_LIBRARIES)[:5])
            self.assertIn(
                f"FAIL audit: manifest libraries match the extracted files and links: {first_five}",
                stdout.getvalue().splitlines(),
            )

    def test_qualify_test_only_profile_selects_fixture_script(self):
        target = "x86_64-unknown-linux-musl"
        archive, manifest_path, manifest = self.qualification_fixture(target, "fixtures")
        manifest_path.write_text(json.dumps(manifest))
        name = archive.name.removesuffix(".tar.xz")
        build.release.create_archive(manifest_path.parents[2], archive, mtime=0, prefix=name)
        work = pathlib.Path(self.temp.name) / "qualification"
        with (
            mock.patch.object(build, "TMP_ROOT", work),
            mock.patch.object(build, "require_native_host"),
            mock.patch.object(build.subprocess, "run", return_value=mock.Mock(returncode=0)) as runner,
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(build.qualify(archive), 0)
        runner.assert_called_once_with(
            ["bash", str(build.ROOT / "tests" / "qualify-fixtures.sh"),
             str(work / "qualify" / name / "path with spaces" / name), target],
            check=False,
        )

    def test_archive_member_problems(self):
        escape = build.tarfile.TarInfo("root/../evil")
        link = build.tarfile.TarInfo("root/link")
        link.type = build.tarfile.SYMTYPE
        outside = build.tarfile.TarInfo("other/file")
        problems = build.archive_member_problems([escape, link, outside], "root")
        self.assertEqual(problems, [
            "unsafe path root/../evil",
            "outside root other/file",
            "link: symlinks are allowed only directly in lib/",
        ])

    def test_archive_member_problems_reports_each_metadata_error(self):
        wrong_owner = build.tarfile.TarInfo("root/owner")
        wrong_owner.uid = 1
        wrong_group = build.tarfile.TarInfo("root/group")
        wrong_group.gid = 1
        unsupported = build.tarfile.TarInfo("root/fifo")
        unsupported.type = build.tarfile.FIFOTYPE
        outside = build.tarfile.TarInfo("other/lib/alias")
        outside.type = build.tarfile.SYMTYPE
        outside.linkname = "missing"
        self.assertEqual(build.archive_member_problems([wrong_owner, wrong_group, unsupported, outside], "root"), [
            "non-normalized owner or mtime: root/owner",
            "non-normalized owner or mtime: root/group",
            "not a file, directory, or symlink: root/fifo",
            "outside root other/lib/alias",
        ])

    def test_extracted_library_problems_preserves_each_missing_field_diagnostic(self):
        payload = self.stage / "lib" / "payload.dylib"
        payload.parent.mkdir(parents=True)
        payload.write_bytes(b"fixture library")
        alias = payload.with_name("alias.dylib")
        alias.symlink_to(payload.name)
        unrelated = self.stage / "XXXX"
        unrelated.write_bytes(b"unrelated archive file")
        libraries = {
            "libavcodec": {"file": "lib/missing.dylib"},
            "libavdevice": {"sha256": hashing.sha256_file(unrelated), "install_name": "@rpath/libavdevice.dylib"},
            "libavutil": {"file": "lib/payload.dylib", "sha256": hashing.sha256_file(payload)},
            "libswscale": {"file": "lib/alias.dylib"},
        }
        self.assertEqual(build.extracted_library_problems(self.stage, libraries, "macos"), [
            "libraries ['libavcodec', 'libavdevice', 'libavutil', 'libswscale']",
            "libavcodec: lib/missing.dylib is not a regular file",
            "libavdevice: None is not a regular file",
            "libavutil: no install_name",
            "libswscale: lib/alias.dylib is not a regular file",
        ])


SONAME_CHAIN = {
    "lib/libavcodec.so": "libavcodec.so.63.4.100",
    "lib/libavcodec.so.63": "libavcodec.so.63.4.100",
}


def linux_runtime_tree():
    regular = set()
    links = {}
    for index, library in enumerate(build.RUNTIME_LIBRARIES):
        real = f"{library}.so.{60 + index}.1.100"
        regular.add(f"lib/{real}")
        links[f"lib/{library}.so.{60 + index}"] = real
        links[f"lib/{library}.so"] = f"{library}.so.{60 + index}"
    return regular, links


class RuntimeProfileTests(unittest.TestCase):
    def test_runtime_is_exactly_the_union_of_tools_and_play_sdk(self):
        runtime, _ = build.load_profile("runtime")
        tools, _ = build.load_profile("tools")
        sdk, _ = build.load_profile("play-sdk")
        for target in runtime["targets"]:
            union = {}
            for profile in (tools, sdk):
                for category, names in build.requested_components(profile, target).items():
                    union.setdefault(category, set()).update(names)
            requested = {category: set(names) for category, names in build.requested_components(runtime, target).items()}
            self.assertEqual(requested, union, target)
            flags = set(build.target_config(runtime, target)["configure_flags"])
            expected = set(build.target_config(tools, target)["configure_flags"]) | set(
                build.target_config(sdk, target)["configure_flags"]
            )
            self.assertEqual(flags, expected, target)
            config = build.target_config(runtime, target)
            for key in ("frameworks", "system_libraries"):
                wanted = set(build.target_config(tools, target)[key]) | set(build.target_config(sdk, target)[key])
                self.assertEqual(set(config[key]), wanted, (target, key))

    def test_runtime_keeps_network_devices_and_ffplay_out(self):
        runtime, _ = build.load_profile("runtime")
        for target in runtime["targets"]:
            requested = build.requested_components(runtime, target)
            self.assertFalse(set(requested["protocols"]) & build.NETWORK_PROTOCOLS)
            self.assertNotIn("devices", requested)
            args = build.configure_args_for(
                runtime, target, build.BUILD_ROOT / "b", build.BUILD_ROOT / "b" / "deps", {"sysroot": "/sdk"}
            )
            for flag in ("--disable-network", "--enable-shared", "--disable-static", "--enable-gpl"):
                self.assertIn(flag, args)
            self.assertIn("--enable-avdevice", args)
            self.assertNotIn("--disable-avdevice", args)
            self.assertLess(args.index("--disable-everything"), args.index("--enable-indev=lavfi"))
            self.assertEqual([arg for arg in args if arg.startswith(("--enable-indev", "--enable-outdev"))], ["--enable-indev=lavfi"])
            self.assertNotIn("--enable-static", args)
            self.assertNotIn("--enable-ffplay", args)
            self.assertNotIn("--pkg-config-flags=--static", args)
            self.assertIn("--enable-ffmpeg", args)
            self.assertIn("--enable-ffprobe", args)

    def test_linux_runtime_search_paths_come_from_response_files(self):
        runtime, _ = build.load_profile("runtime")
        args = build.configure_args_for(
            runtime, "x86_64-unknown-linux-musl", build.BUILD_ROOT / "b", build.BUILD_ROOT / "b" / "deps", {}
        )
        exe = next(arg for arg in args if arg.startswith("--extra-ldexeflags="))
        so = next(arg for arg in args if arg.startswith("--extra-ldsoflags="))
        self.assertIn("-Wl,@../ld-program.rsp", exe)
        self.assertIn("-Wl,@../ld-library.rsp", so)
        for flags in (exe, so):
            self.assertIn("-Wl,-z,stack-size=2097152", flags)
            self.assertNotIn("$", flags)
            self.assertNotIn("-static-pie", flags)
        self.assertFalse(any(str(build.ROOT) in arg for arg in args))
        self.assertEqual(build.linker_response("$ORIGIN/../lib").split(), ["--enable-new-dtags", "-rpath", "$ORIGIN/../lib"])

    def test_macos_runtime_uses_rpath_install_names(self):
        runtime, _ = build.load_profile("runtime")
        args = build.configure_args_for(
            runtime, "aarch64-apple-darwin", build.BUILD_ROOT / "b", build.BUILD_ROOT / "b" / "deps", {"sysroot": "/sdk"}
        )
        self.assertIn("--install-name-dir=@rpath", args)
        self.assertIn("--extra-ldexeflags=-Wl,-rpath,@loader_path/../lib", args)
        self.assertIn("--extra-ldsoflags=-Wl,-rpath,@loader_path", args)

    def test_runtime_archive_name(self):
        parsed = build.parse_archive_name("ffmpeg-runtime-9.0.2-aarch64-unknown-linux-musl.tar.xz")
        self.assertEqual(parsed["profile"], "runtime")
        self.assertEqual(parsed["target"], "aarch64-unknown-linux-musl")


class LicenseAndDeviceTests(unittest.TestCase):
    def test_profile_licenses(self):
        expected = {"play-sdk": "lgpl", "tools": "gpl", "runtime": "gpl", "fixtures": "gpl"}
        for name, license_name in expected.items():
            profile, _ = build.load_profile(name)
            self.assertEqual(profile["license"], license_name)
        self.assertEqual(build.FFMPEG_LICENSES["gpl"]["ffmpeg_license"], "GPL version 2 or later")
        self.assertEqual(build.FFMPEG_LICENSES["lgpl"]["ffmpeg_license"], "LGPL version 2.1 or later")

    def test_gpl_profiles_ship_the_gpl_text(self):
        tools, _ = build.load_profile("tools")
        sdk, _ = build.load_profile("play-sdk")
        self.assertIn("share/licenses/ffmpeg/COPYING.GPLv2", build.notice_paths(tools))
        self.assertNotIn("share/licenses/ffmpeg/COPYING.GPLv2", build.notice_paths(sdk))
        self.assertIn("share/licenses/ffmpeg/COPYING.LGPLv2.1", build.notice_paths(sdk))

    def test_play_sdk_stays_lgpl_without_devices(self):
        sdk, _ = build.load_profile("play-sdk")
        for target in sdk["targets"]:
            args = build.configure_args_for(sdk, target, build.BUILD_ROOT / "b", build.BUILD_ROOT / "b" / "deps", {"sysroot": "/sdk"})
            self.assertIn("--disable-avdevice", args)
            self.assertNotIn("--enable-gpl", args)
            self.assertFalse(any(arg.startswith("--enable-indev") for arg in args))

    def test_tools_requests_lavfi_as_an_input_device(self):
        tools, _ = build.load_profile("tools")
        requested = build.requested_components(tools, "x86_64-unknown-linux-musl")
        self.assertEqual(requested["indevs"], ["lavfi"])
        self.assertNotIn("lavfi", requested["demuxers"])

    def test_only_lavfi_input_device_may_be_requested(self):
        profile = {"profile": "x", "components": {"indevs": ["lavfi", "v4l2"]}, "targets": {"t": {"platform": "linux", "arch": "x86_64"}}}
        with self.assertRaises(SystemExit):
            build.requested_components(profile, "t")

    def test_license_problems(self):
        self.assertEqual(build.license_problems("gpl", "CONFIG_GPL=yes\n!CONFIG_NONFREE=yes\n"), [])
        self.assertEqual(build.license_problems("lgpl", "!CONFIG_GPL=yes\n"), [])
        self.assertEqual(len(build.license_problems("lgpl", "CONFIG_GPL=yes\n")), 1)
        self.assertEqual(len(build.license_problems("gpl", "!CONFIG_GPL=yes\n")), 1)
        self.assertEqual(build.license_problems("gpl", "CONFIG_GPL=yes\nCONFIG_NONFREE=yes\nCONFIG_VERSION3=yes\n"), ["CONFIG_NONFREE=yes", "CONFIG_VERSION3=yes"])

    def test_device_problems(self):
        requested = {"indevs": ["lavfi"]}
        self.assertEqual(build.device_problems(requested, {"indevs": ["lavfi"]}), [])
        self.assertEqual(build.device_problems(requested, {"indevs": ["lavfi", "v4l2"]}), ["v4l2"])
        self.assertEqual(build.device_problems({}, {"indevs": ["lavfi"]}), ["lavfi"])
        problems = build.component_problems(requested, {"indevs": ["lavfi"], "outdevs": ["sdl2"]})
        self.assertEqual(problems, ["outdevs enabled: ['sdl2']"])


class FixturesProfileTests(unittest.TestCase):
    def test_profile_is_gpl_test_only_tools(self):
        profile, _ = build.load_profile("fixtures")
        self.assertEqual(profile["license"], "gpl")
        self.assertEqual(profile["artifact"], "tools")
        self.assertTrue(profile["test_only"])
        for source in ("zlib", "x264", "x265", "svtav1", "vpx", "lame", "opus"):
            self.assertIn(source, profile["sources"])

    def test_profile_is_linux_x86_64_only(self):
        profile, _ = build.load_profile("fixtures")
        self.assertEqual(list(profile["targets"]), ["x86_64-unknown-linux-musl"])
        self.assertEqual(build.profile_target_problems(profile), [])
        with self.assertRaises(SystemExit):
            build.configure_args_for(
                profile, "aarch64-apple-darwin", build.BUILD_ROOT / "b", build.BUILD_ROOT / "b" / "deps", {}
            )

    def test_test_only_profile_rules(self):
        macos = {
            "test_only": True,
            "artifact": "tools",
            "targets": {"aarch64-apple-darwin": {"platform": "macos"}},
        }
        self.assertEqual(
            build.profile_target_problems(macos),
            ["a test-only profile builds only Linux targets, not ['aarch64-apple-darwin']"],
        )
        runtime = {
            "test_only": True,
            "artifact": "runtime",
            "targets": {"x86_64-unknown-linux-musl": {"platform": "linux"}},
        }
        self.assertEqual(
            build.profile_target_problems(runtime),
            ["a test-only profile must use the tools artifact"],
        )
        self.assertEqual(
            build.profile_target_problems(
                {
                    "test_only": False,
                    "artifact": "runtime",
                    "targets": {"aarch64-apple-darwin": {"platform": "macos"}},
                }
            ),
            [],
        )

    def test_configure_enables_the_fixture_encoders(self):
        profile, _ = build.load_profile("fixtures")
        args = build.configure_args_for(
            profile,
            "x86_64-unknown-linux-musl",
            build.BUILD_ROOT / "b",
            build.BUILD_ROOT / "b" / "deps",
            {},
        )
        for flag in (
            "--enable-libx264",
            "--enable-libx265",
            "--enable-libsvtav1",
            "--enable-libvpx",
            "--enable-libmp3lame",
            "--enable-libopus",
            "--enable-gpl",
            "--enable-indev=lavfi",
            "--disable-network",
        ):
            self.assertIn(flag, args)
        self.assertNotIn("--enable-libdav1d", args)
        self.assertNotIn("--enable-shared", args)
        self.assertIn("--disable-shared", args)

    def test_notices_cover_every_dependency(self):
        profile, _ = build.load_profile("fixtures")
        notices = build.notice_paths(profile)
        for relative in (
            "share/licenses/ffmpeg/COPYING.GPLv2",
            "share/licenses/zlib/LICENSE",
            "share/licenses/x264/COPYING",
            "share/licenses/x265/COPYING",
            "share/licenses/svtav1/LICENSE.md",
            "share/licenses/vpx/LICENSE",
            "share/licenses/lame/COPYING",
            "share/licenses/opus/COPYING",
        ):
            self.assertIn(relative, notices)

    def test_fixtures_archive_is_named_for_its_profile(self):
        self.assertEqual(
            release.archive_name("ffmpeg-fixtures", "9.0.2", "x86_64-unknown-linux-musl"),
            "ffmpeg-fixtures-9.0.2-x86_64-unknown-linux-musl.tar.xz",
        )


class SymlinkTests(unittest.TestCase):
    def test_accepts_soname_links(self):
        self.assertEqual(build.symlink_problems(SONAME_CHAIN, {"lib/libavcodec.so.63.4.100"}), [])

    def test_accepts_chain_inside_lib(self):
        links = {"lib/libavcodec.so": "libavcodec.so.63", "lib/libavcodec.so.63": "libavcodec.so.63.4.100"}
        self.assertEqual(build.symlink_problems(links, {"lib/libavcodec.so.63.4.100"}), [])
        self.assertEqual(build.resolve_link("lib/libavcodec.so", links), "lib/libavcodec.so.63.4.100")

    def assertRejected(self, links, regular, reason):
        problems = build.symlink_problems(links, regular)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn(reason, problems[0])

    def test_rejects_absolute_target(self):
        self.assertRejected({"lib/libz.so": "/usr/lib/libz.so.1"}, set(), "absolute")

    def test_rejects_escaping_targets(self):
        for target in ("../share/x", "../../../etc/passwd", "..", "pkgconfig/libavcodec.pc", "./libavcodec.so.63"):
            self.assertRejected({"lib/libavcodec.so": target}, {"share/x", "lib/pkgconfig/libavcodec.pc"}, "not a sibling in lib/")

    def test_rejects_dangling(self):
        self.assertRejected({"lib/libavcodec.so": "libavcodec.so.63.4.100"}, set(), "dangling")

    def test_rejects_links_outside_lib(self):
        for link in ("bin/ffmpeg", "lib/pkgconfig/libavcodec.pc", "libavcodec.so"):
            self.assertRejected({link: "libavcodec.so.63.4.100"}, {"lib/libavcodec.so.63.4.100"}, "only directly in lib/")

    def test_rejects_cycle(self):
        problems = build.symlink_problems({"lib/a.so": "b.so", "lib/b.so": "a.so"}, set())
        self.assertEqual(len(problems), 2)
        self.assertTrue(all("cycle" in problem for problem in problems))

    def test_rejects_chain_that_leaves_lib(self):
        links = {"lib/libavcodec.so": "libavcodec.so.63", "lib/libavcodec.so.63": "../escape"}
        problems = build.symlink_problems(links, {"escape"})
        self.assertEqual(len(problems), 2)
        self.assertTrue(all("not a sibling in lib/" in problem for problem in problems))


class LibraryLayoutTests(unittest.TestCase):
    def test_linux_layout(self):
        regular, links = linux_runtime_tree()
        layout, problems = build.library_layout(regular | {"bin/ffmpeg"}, links, "linux")
        self.assertEqual(problems, [])
        self.assertEqual(
            layout["libavcodec"],
            {"file": "lib/libavcodec.so.60.1.100", "links": ["lib/libavcodec.so", "lib/libavcodec.so.60"], "major": 60},
        )
        self.assertEqual(build.library_identity_name("libavcodec", 60, "linux"), "libavcodec.so.60")

    def test_macos_layout(self):
        regular = set()
        links = {}
        for library in build.RUNTIME_LIBRARIES:
            regular.add(f"lib/{library}.61.2.100.dylib")
            links[f"lib/{library}.61.dylib"] = f"{library}.61.2.100.dylib"
            links[f"lib/{library}.dylib"] = f"{library}.61.2.100.dylib"
        layout, problems = build.library_layout(regular, links, "macos")
        self.assertEqual(problems, [])
        self.assertEqual(layout["libswscale"]["links"], ["lib/libswscale.61.dylib", "lib/libswscale.dylib"])
        self.assertEqual(build.library_identity_name("libswscale", 61, "macos"), "@rpath/libswscale.61.dylib")

    def test_layout_rejects_missing_links_and_extra_libraries(self):
        regular, links = linux_runtime_tree()
        del links["lib/libavutil.so"]
        regular.add("lib/libdav1d.so.7.0.0")
        regular.add("lib/libavcodec.a")
        _, problems = build.library_layout(regular, links, "linux")
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("missing symlink lib/libavutil.so", problems[0])
        self.assertIn("lib/libdav1d.so.7.0.0", problems[1])
        self.assertIn("lib/libavcodec.a", problems[1])

    def test_layout_rejects_link_to_wrong_library(self):
        regular, links = linux_runtime_tree()
        links["lib/libavcodec.so"] = "libavutil.so.63.1.100"
        _, problems = build.library_layout(regular, links, "linux")
        self.assertEqual(problems, ["libavcodec: lib/libavcodec.so does not resolve to lib/libavcodec.so.60.1.100"])

    def test_layout_reports_duplicate_libraries_and_unclaimed_links(self):
        regular, links = linux_runtime_tree()
        regular.add("lib/libavcodec.so.60.2.100")
        links["lib/libdav1d.so"] = "libdav1d.so.7.0.0"
        layout, problems = build.library_layout(regular, links, "linux")
        self.assertEqual(set(layout), set(build.RUNTIME_LIBRARIES) - {"libavcodec"})
        self.assertEqual(problems, [
            (
                "libavcodec: expected one versioned library file, found "
                "['lib/libavcodec.so.60.1.100', 'lib/libavcodec.so.60.2.100']"
            ),
            "unexpected files in lib/: ['lib/libavcodec.so.60.1.100', 'lib/libavcodec.so.60.2.100']",
            "unexpected symlinks: ['lib/libavcodec.so', 'lib/libavcodec.so.60', 'lib/libdav1d.so']",
        ])


READELF_DYNAMIC = """
Dynamic section at offset 0x1c3d8 contains 30 entries:
  Tag        Type                         Name/Value
 0x0000000000000001 (NEEDED)             Shared library: [libavutil.so.61]
 0x0000000000000001 (NEEDED)             Shared library: [libva.so.2]
 0x0000000000000001 (NEEDED)             Shared library: [libc.musl-x86_64.so.1]
 0x000000000000000e (SONAME)             Library soname: [libavcodec.so.63]
 0x000000000000001d (RUNPATH)            Library runpath: [$ORIGIN]
 0x000000000000001e (FLAGS)              BIND_NOW
"""

OTOOL_LOAD_COMMANDS = """bin/ffmpeg:
Load command 0
      cmd LC_SEGMENT_64
  cmdsize 72
  segname __PAGEZERO
Load command 4
          cmd LC_ID_DYLIB
      cmdsize 56
         name @rpath/libavcodec.63.dylib (offset 24)
   time stamp 1 Thu Jan  1 00:00:01 1970
Load command 12
          cmd LC_LOAD_DYLIB
      cmdsize 56
         name @rpath/libavutil.61.dylib (offset 24)
Load command 13
          cmd LC_LOAD_DYLIB
      cmdsize 96
         name /System/Library/Frameworks/VideoToolbox.framework/Versions/A/VideoToolbox (offset 24)
Load command 14
          cmd LC_RPATH
      cmdsize 32
         path @loader_path (offset 12)
"""


class BinaryInspectionTests(unittest.TestCase):
    def test_elf_records_legacy_rpath_and_standalone_textrel(self):
        dynamic = build.elf_dynamic(
            " 0x000A (RPATH) Library rpath: [$ORIGIN:$ORIGIN/lib]\n"
            " 0x000B (TEXTREL) 0x0\n"
            " 0x000C (AUXILIARY) Auxiliary library: [fixture.so]\n"
        )
        self.assertEqual(dynamic, {
            "needed": [], "soname": None, "runpath": [],
            "rpath": ["$ORIGIN", "$ORIGIN/lib"], "textrel": True,
        })

    def test_macho_executable_has_no_install_name(self):
        commands = build.macho_load_commands(
            "Load command 0\n"
            "          cmd LC_LOAD_DYLIB\n"
            "         name /usr/lib/libSystem.B.dylib (offset 24)\n"
        )
        self.assertEqual(commands, {"id": None, "rpaths": [], "loads": ["/usr/lib/libSystem.B.dylib"]})

    def test_elf_dynamic(self):
        dynamic = build.elf_dynamic(READELF_DYNAMIC)
        self.assertEqual(dynamic["needed"], ["libavutil.so.61", "libva.so.2", "libc.musl-x86_64.so.1"])
        self.assertEqual(dynamic["soname"], "libavcodec.so.63")
        self.assertEqual(dynamic["runpath"], ["$ORIGIN"])
        self.assertEqual(dynamic["rpath"], [])
        self.assertFalse(dynamic["textrel"])
        self.assertTrue(build.elf_dynamic(" 0x000000000000001e (FLAGS)              TEXTREL BIND_NOW\n")["textrel"])

    def test_macho_load_commands(self):
        commands = build.macho_load_commands(OTOOL_LOAD_COMMANDS)
        self.assertEqual(commands["id"], "@rpath/libavcodec.63.dylib")
        self.assertEqual(commands["rpaths"], ["@loader_path"])
        self.assertEqual(
            commands["loads"],
            ["@rpath/libavutil.61.dylib", "/System/Library/Frameworks/VideoToolbox.framework/Versions/A/VideoToolbox"],
        )

    def test_foreign_elf_needed(self):
        profile, _ = build.load_profile("runtime")
        config = build.target_config(profile, "x86_64-unknown-linux-musl")
        siblings = {"libavutil.so.61", "libavcodec.so.63"}
        allowed = ["libavutil.so.61", "libc.musl-x86_64.so.1", "libva.so.2", "libva-drm.so.2"]
        self.assertEqual(build.foreign_elf_needed(allowed, siblings, config), [])
        forbidden = ["libgcc_s.so.1", "libstdc++.so.6", "libz.so.1", "libdav1d.so.7", "libc.musl-aarch64.so.1", "libdrm.so.2"]
        self.assertEqual(build.foreign_elf_needed(allowed + forbidden, siblings, config), sorted(forbidden))

    def test_foreign_macho_loads(self):
        profile, _ = build.load_profile("runtime")
        config = build.target_config(profile, "aarch64-apple-darwin")
        siblings = {"@rpath/libavutil.61.dylib"}
        loads = [
            "@rpath/libavutil.61.dylib",
            "/usr/lib/libSystem.B.dylib",
            "/System/Library/Frameworks/AudioToolbox.framework/Versions/A/AudioToolbox",
        ]
        self.assertEqual(build.foreign_macho_loads(loads, siblings, config), [])
        foreign = [
            "/usr/lib/libz.1.dylib",
            "/opt/homebrew/lib/libdav1d.7.dylib",
            "@rpath/libdav1d.7.dylib",
            "/System/Library/Frameworks/AppKit.framework/Versions/C/AppKit",
        ]
        self.assertEqual(build.foreign_macho_loads(loads + foreign, siblings, config), sorted(foreign))

    def test_bundled_symbol_exports(self):
        nm = "0000000000001000 T avcodec_open2\n0000000000000000 A LIBAVCODEC_63\n0000000000002000 T dav1d_open\n0000000000003000 T inflateInit2_\n"
        self.assertEqual(build.bundled_symbol_exports(build.exported_symbols(nm)), ["dav1d_open", "inflateInit2_"])
        self.assertEqual(build.bundled_symbol_exports(["_av_malloc", "_swr_alloc", "_dav1d_version"]), ["_dav1d_version"])

    def test_ffmpeg_listings(self):
        protocols = "Supported file protocols:\nInput:\n  fd\n  file\n  pipe\nOutput:\n  fd\n  file\n  pipe\n"
        self.assertEqual(build.ffmpeg_protocols(protocols), {"fd", "file", "pipe"})
        encoders = (
            "Encoders:\n V..... = Video\n A..... = Audio\n ------\n"
            " V....D png                  PNG (Portable Network Graphics) image\n"
            " S..... mov_text             3GPP Timed Text subtitle\n"
        )
        self.assertEqual(build.ffmpeg_codec_names(encoders), {"png", "mov_text"})
        self.assertEqual(build.ffmpeg_hwaccel_types("Hardware acceleration methods:\nvaapi\n\n"), {"vaapi"})


RUNTIME_PC = """prefix=${pcfiledir}/../..
exec_prefix=${prefix}
libdir=${prefix}/lib
includedir=${prefix}/include

Name: libavcodec
Description: FFmpeg codec library
Version: 63.4.100
Requires:
Requires.private: libswresample >= 6.4.100, libavutil >= 61.3.100
Conflicts:
Libs: -L${libdir}  -lavcodec
Libs.private:
Cflags: -I${includedir}
"""


class RuntimeLinkAuditTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".work/tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        directory = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory(dir=scratch)))
        self.binary = directory / "fixture"
        self.profile, _ = build.load_profile("runtime")

    def test_elf_checks_program_and_library_loader_contracts(self):
        config = build.target_config(self.profile, "x86_64-unknown-linux-musl")
        for role in ("program", "library"):
            for valid in (True, False):
                with self.subTest(role=role, valid=valid):
                    kind = "pie executable" if role == "program" else "shared object"
                    search = "$ORIGIN/../lib" if role == "program" else "$ORIGIN"
                    loader = "/lib/ld-musl-x86_64.so.1"
                    file_kind = f"ELF 64-bit {kind}, x86-64" if valid else f"data {kind}, x86-64"
                    leaked = [f"dav1d_fixture{index:02d}" for index in range(11)]
                    self.binary.write_bytes(b"fixture" if valid else b"GLIBC_fixture")
                    responses = {
                        ("file", "-b"): file_kind,
                        ("readelf", "-dW"): (
                            f" 0x1 (NEEDED) Shared library: [libc.musl-x86_64.so.1]\n"
                            f" 0x1 (RUNPATH) Library runpath: [{search}]\n"
                        ) if valid else (
                            " 0x1 (NEEDED) Shared library: [libforeign.so]\n"
                            " 0x1 (RPATH) Library rpath: [/legacy]\n"
                            " 0x1 (TEXTREL) 0x0\n"
                        ),
                        ("readelf", "-lW"): (
                            "Program Headers:\n"
                            " GNU_STACK 0x0 0x0 0x0 0x0 0x200000 RW 0x4\n"
                            f" [Requesting program interpreter: {loader}]\n" if valid else
                            " GNU_STACK 0x0 0x0 0x0 0x0 0x100000 RW 0x4\n"
                        ),
                        ("nm", "-D", "--defined-only"): (
                            "0000000000001000 T avcodec_open2\n" if valid else
                            "".join(f"0000000000001000 T {symbol}\n" for symbol in leaked)
                        ),
                    }
                    case = mock.Mock()
                    with mock.patch.object(
                        build, "output", side_effect=lambda args, reports=responses: reports[tuple(args[:-1])],
                    ) as inspect:
                        build.audit_runtime_elf(case, config, self.binary, role, set())
                    self.assertEqual(
                        [(call.args[0], bool(call.args[1])) for call in case.call_args_list],
                        [
                            (f"fixture is an x86-64 ELF {kind}", valid),
                            ("fixture NEEDED only libav*, musl, and system libraries", valid),
                            (f"fixture RUNPATH is {search}", valid),
                            ("fixture has no RPATH", valid),
                            ("fixture has no text relocations", valid),
                            ("fixture thread stack is 2097152 B", valid),
                            (f"fixture interpreter is {loader}" if role == "program" else
                             "fixture exports no dav1d or zlib symbols", valid),
                            ("fixture has no glibc symbol versions", valid),
                        ],
                    )
                    if not valid:
                        details = {call.args[0]: call.args[2:] for call in case.call_args_list}
                        self.assertEqual(details[f"fixture is an x86-64 ELF {kind}"], (file_kind,))
                        self.assertEqual(details["fixture NEEDED only libav*, musl, and system libraries"], ("foreign: ['libforeign.so']",))
                        self.assertEqual(details[f"fixture RUNPATH is {search}"], ("RUNPATH []",))
                        self.assertEqual(details["fixture has no RPATH"], ("RPATH ['/legacy']",))
                        self.assertEqual(details["fixture thread stack is 2097152 B"], ("PT_GNU_STACK size 1048576",))
                        if role == "program":
                            self.assertEqual(details[f"fixture interpreter is {loader}"], ("found None",))
                        else:
                            self.assertEqual(details["fixture exports no dav1d or zlib symbols"], (f"exports: {leaked[:10]}",))
                    self.assertTrue(all(call.args[0][-1] == str(self.binary) for call in inspect.call_args_list))

    def test_macho_checks_program_and_library_load_and_signature_contracts(self):
        config = build.target_config(self.profile, "aarch64-apple-darwin")
        for role in ("program", "library"):
            for valid in (True, False):
                with self.subTest(role=role, valid=valid):
                    kind = "executable" if role == "program" else "dynamically linked shared library"
                    search = "@loader_path/../lib" if role == "program" else "@loader_path"
                    file_kind = f"Mach-O 64-bit {kind} {'arm64' if valid else 'x86_64'}"
                    leaked = [f"_dav1d_fixture{index:02d}" for index in range(11)]
                    responses = {
                        ("file", "-b"): file_kind,
                        ("otool", "-l"): (
                            "Load command 0\n cmd LC_RPATH\n"
                            f" path {search if valid else '/wrong'} (offset 12)\n"
                            "Load command 1\n cmd LC_LOAD_DYLIB\n"
                            f" name {'/usr/lib/libSystem.B.dylib' if valid else '/usr/lib/libz.1.dylib'} (offset 24)\n"
                            "Load command 2\n cmd LC_LOAD_DYLIB\n"
                            " name /System/Library/Frameworks/AudioToolbox.framework/AudioToolbox (offset 24)\n"
                        ),
                        ("nm", "-gU"): (
                            "0000000000001000 T _avcodec_open2\n" if valid else
                            "".join(f"0000000000001000 T {symbol}\n" for symbol in leaked)
                        ),
                    }
                    status = 0 if valid else 1
                    signature = subprocess.CompletedProcess([], status, "", "signature invalid" if status else "")
                    case = mock.Mock()
                    with (
                        mock.patch.object(
                            build, "output", side_effect=lambda args, reports=responses: reports[tuple(args[:-1])],
                        ) as inspect,
                        mock.patch.object(build.subprocess, "run", return_value=signature) as sign,
                    ):
                        build.audit_runtime_macho(case, config, self.binary, role, set())
                    labels = [
                        f"fixture is a Mach-O arm64 {kind}",
                        "fixture loads only libav*, libSystem, and profile frameworks",
                        f"fixture LC_RPATH is {search}",
                        "fixture links no dynamic zlib",
                        "fixture code signature verifies",
                    ]
                    if role == "library":
                        labels.append("fixture exports no dav1d or zlib symbols")
                    self.assertEqual(
                        [(call.args[0], bool(call.args[1])) for call in case.call_args_list],
                        [(label, valid) for label in labels],
                    )
                    if not valid:
                        details = {call.args[0]: call.args[2:] for call in case.call_args_list}
                        self.assertEqual(details[labels[0]], (file_kind,))
                        self.assertEqual(details[labels[1]], ("foreign: ['/usr/lib/libz.1.dylib']",))
                        self.assertEqual(details[labels[2]], ("LC_RPATH ['/wrong']",))
                        self.assertEqual(details["fixture code signature verifies"], ("signature invalid",))
                        if role == "library":
                            self.assertEqual(details["fixture exports no dav1d or zlib symbols"], (f"exports: {leaked[:10]}",))
                    self.assertTrue(all(call.args[0][-1] == str(self.binary) for call in inspect.call_args_list))
                    sign.assert_called_once_with(
                        ["codesign", "--verify", "--strict", str(self.binary)], capture_output=True, text=True, check=False,
                    )


class RuntimeStageTests(unittest.TestCase):
    def setUp(self):
        build.TMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=build.TMP_ROOT)
        self.root = pathlib.Path(self.temp.name)
        self.stage = self.root / "stage"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, data=b"x"):
        path = self.stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def link(self, relative, target):
        path = self.stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)

    def test_runtime_pc_is_shared_only_and_relocatable(self):
        pc = self.write(
            "lib/pkgconfig/libavcodec.pc",
            RUNTIME_PC.replace("${pcfiledir}/../..", "/opt/ffmpeg-build")
            .replace("Libs.private:", f"Libs.private: -L{self.root}/deps/lib -ldav1d -lz -lm -lva")
            .encode(),
        )
        self.assertTrue(build.pc_problems(pc.read_text()))
        build.normalize_pc(self.stage)
        build.drop_static_link_flags(self.stage)
        self.assertEqual(build.pc_problems(pc.read_text()), [])
        self.assertIn("Libs.private:\n", pc.read_text())
        self.assertIn("Requires.private: libswresample", pc.read_text())

    def test_pc_problems(self):
        self.assertEqual(build.pc_problems(RUNTIME_PC), [])
        self.assertEqual(len(build.pc_problems(RUNTIME_PC.replace("-lavcodec", "-lavcodec -ldav1d"))), 1)
        self.assertEqual(len(build.pc_problems(RUNTIME_PC.replace("-I${includedir}", "-I/usr/include"))), 1)
        self.assertEqual(len(build.pc_problems(RUNTIME_PC.replace("Libs.private:", "Libs.private: -lz"))), 1)

    def test_prune_runtime_stage_keeps_libraries_and_headers(self):
        for relative in ("bin/ffmpeg", "bin/ffprobe", "lib/libavcodec.so.63.4.100", "include/libavutil/avutil.h", "share/man/man1/ffmpeg.1"):
            self.write(relative)
        self.link("lib/libavcodec.so", "libavcodec.so.63.4.100")
        build.prune_stage(self.stage, "runtime")
        self.assertTrue((self.stage / "bin" / "ffmpeg").is_file())
        self.assertTrue((self.stage / "lib" / "libavcodec.so").is_symlink())
        self.assertTrue((self.stage / "include" / "libavutil" / "avutil.h").is_file())
        self.assertFalse((self.stage / "share" / "man").exists())

    def test_stage_links_keep_soname_links(self):
        self.write("lib/libavcodec.so.63.4.100", b"elf")
        for link, target in SONAME_CHAIN.items():
            self.link(link, target)
        self.assertEqual(build.stage_links(self.stage), SONAME_CHAIN)

    def test_stage_links_reject_unsafe_links(self):
        outside = self.write("../outside.so")
        cases = {
            "lib/libz.so": str(outside),
            "lib/libescape.so": "../../outside.so",
            "lib/libdangling.so": "libmissing.so.1",
            "bin/ffmpeg": "../lib/libavcodec.so.63.4.100",
        }
        self.write("lib/libavcodec.so.63.4.100")
        for link, target in cases.items():
            with self.subTest(link=link):
                self.link(link, target)
                with self.assertRaises(SystemExit):
                    build.stage_links(self.stage)
                (self.stage / link).unlink()

    def test_stage_links_reject_symlinked_directory(self):
        self.write("lib/real/libavcodec.so.63.4.100")
        self.link("lib/linked", "real")
        with self.assertRaises(SystemExit):
            build.stage_links(self.stage)

    def test_archive_round_trips_soname_links(self):
        self.write("lib/libavcodec.so.63.4.100", b"elf")
        self.write("bin/ffmpeg", b"exe")
        for link, target in SONAME_CHAIN.items():
            self.link(link, target)
        archive_path = release.create_archive(self.stage, self.root / "first.tar.xz", mtime=0, prefix="root")
        destination = self.root / "out"
        with build.tarfile.open(archive_path) as archive:
            members = archive.getmembers()
            self.assertEqual(build.archive_member_problems(members, "root"), [])
            archive.extractall(destination, filter="data")
        links = {member.name: member.linkname for member in members if member.issym()}
        self.assertEqual(links, {f"root/{link}": target for link, target in SONAME_CHAIN.items()})
        extracted = destination / "root" / "lib" / "libavcodec.so"
        self.assertTrue(extracted.is_symlink())
        self.assertEqual(extracted.read_bytes(), b"elf")

    def test_archive_member_problems_reject_unsafe_links(self):
        def member(name, linkname=None):
            info = build.tarfile.TarInfo(name)
            if linkname is not None:
                info.type = build.tarfile.SYMTYPE
                info.linkname = linkname
            return info

        real = member("root/lib/libavcodec.so.63.4.100")
        for name, linkname in (
            ("root/lib/libavcodec.so", "/usr/lib/libavcodec.so.63"),
            ("root/lib/libavcodec.so", "../../../etc/passwd"),
            ("root/lib/libavcodec.so", "libavcodec.so.62.0.0"),
            ("root/bin/ffmpeg", "../lib/libavcodec.so.63.4.100"),
        ):
            with self.subTest(name=name, linkname=linkname):
                problems = build.archive_member_problems([real, member(name, linkname)], "root")
                self.assertEqual(len(problems), 1, problems)
        hardlink = member("root/lib/libavcodec.so")
        hardlink.type = build.tarfile.LNKTYPE
        hardlink.linkname = "root/lib/libavcodec.so.63.4.100"
        self.assertEqual(len(build.archive_member_problems([real, hardlink], "root")), 1)

    def test_runtime_stage_complete_needs_development_links(self):
        runtime, _ = build.load_profile("runtime")
        for relative in build.notice_paths(runtime):
            self.write(relative)
        for relative in ("bin/ffmpeg", "bin/ffprobe", "include/libavutil/ffversion.h", "share/ffmpeg-build/manifest.json"):
            self.write(relative)
        for library in build.RUNTIME_LIBRARIES:
            self.write(f"lib/pkgconfig/{library}.pc")
            self.write(f"lib/{library}.so.1.0.0")
        runtime, _ = build.load_profile("runtime")
        self.assertFalse(build.stage_complete(self.stage, runtime, "linux"))
        for library in build.RUNTIME_LIBRARIES:
            self.link(f"lib/{library}.so", f"{library}.so.1.0.0")
        self.assertTrue(build.stage_complete(self.stage, runtime, "linux"))
        self.assertFalse(build.stage_complete(self.stage, runtime, "macos"))
        (self.stage / "share/licenses/ffmpeg/COPYING.GPLv2").unlink()
        self.assertFalse(build.stage_complete(self.stage, runtime, "linux"))

    def test_extracted_library_problems(self):
        real = self.write("lib/libavcodec.so.63.4.100", b"elf")
        for link, target in SONAME_CHAIN.items():
            self.link(link, target)
        entry = {
            "file": "lib/libavcodec.so.63.4.100",
            "links": sorted(SONAME_CHAIN),
            "soname": "libavcodec.so.63",
            "sha256": hashing.sha256_file(real),
        }
        libraries = {library: dict(entry) for library in build.RUNTIME_LIBRARIES}
        self.assertEqual(build.extracted_library_problems(self.stage, libraries, "linux"), [])
        libraries["libavcodec"]["sha256"] = "0" * 64
        libraries["libavutil"]["links"] = ["lib/libavutil.so"]
        problems = build.extracted_library_problems(self.stage, libraries, "linux")
        self.assertEqual(len(problems), 2, problems)


class StaticPkgConfigTests(unittest.TestCase):
    def test_x265_pc_loses_only_the_shared_libgcc(self):
        with tempfile.TemporaryDirectory() as tmp:
            pc = pathlib.Path(tmp) / "x265.pc"
            pc.write_text(
                "Libs: -L${libdir} -lx265\n"
                "Libs.private: -lstdc++ -lm -lssp_nonshared -lgcc_s -lgcc -lgcc_s -lgcc -lrt -ldl\n"
            )
            build.drop_shared_libgcc(pc)
            self.assertEqual(
                pc.read_text(),
                "Libs: -L${libdir} -lx265\n"
                "Libs.private: -lstdc++ -lm -lssp_nonshared -lgcc -lgcc -lrt -ldl\n",
            )


    def test_vpx_pc_points_at_the_real_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            pc = pathlib.Path(tmp) / "vpx.pc"
            pc.write_text("prefix=/opt/ffmpeg-build\nexec_prefix=${prefix}\nLibs: -L${libdir} -lvpx -lm\n")
            build.set_pc_prefix(pc, pathlib.Path("/deps"))
            self.assertEqual(pc.read_text(), "prefix=/deps\nexec_prefix=${prefix}\nLibs: -L${libdir} -lvpx -lm\n")

    def test_feature_flags_are_not_external_libraries(self):
        config_mak = "CONFIG_LIBX264=yes\nCONFIG_LIBX264_HDR10=yes\nCONFIG_LIBX264_ENCODER=yes\n"
        self.assertEqual(build.parse_external_libraries(config_mak), ["x264"])

if __name__ == "__main__":
    unittest.main()
