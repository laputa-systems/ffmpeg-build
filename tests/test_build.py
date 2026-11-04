import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build  # noqa: E402


class ProfileTests(unittest.TestCase):
    def test_profiles_declare_target_scope(self):
        for name in ("play-sdk", "tools"):
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
        for source in lock["sources"].values():
            self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")

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
        parsed = build.parse_archive_name("ffmpeg-9.0.2+20261104-r2-x86_64-unknown-linux-musl-play-sdk.tar.gz")
        self.assertEqual(
            parsed,
            {"upstream": "9.0.2", "tag": "20261104-r2", "target": "x86_64-unknown-linux-musl", "profile": "play-sdk"},
        )
        parsed = build.parse_archive_name("ffmpeg-9.0.2+local-aarch64-apple-darwin-tools.tar.gz")
        self.assertEqual(parsed["target"], "aarch64-apple-darwin")
        with self.assertRaises(SystemExit):
            build.parse_archive_name("ffmpeg-9.0.2-aarch64-apple-darwin-tools.tar.gz")

    def test_release_tag_format(self):
        for tag in ("20261104", "20261104-r2", "local"):
            self.assertTrue(build.RELEASE_TAG.match(tag), tag)
        for tag in ("2026-11-04", "20261104-2", "latest", "20261104+x"):
            self.assertFalse(build.RELEASE_TAG.match(tag), tag)

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

    def test_deterministic_archive(self):
        files = {"bin/ffmpeg": (b"binary", True), "README": (b"readme", False)}
        first = self.stage / "first.tar.gz"
        second = self.stage / "second.tar.gz"
        build.write_deterministic_archive(first, "root", files)
        build.write_deterministic_archive(second, "root", dict(reversed(list(files.items()))))
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with build.tarfile.open(first) as archive:
            members = archive.getmembers()
        self.assertEqual([member.name for member in members], ["root", "root/bin", "root/README", "root/bin/ffmpeg"])
        self.assertEqual(build.archive_member_problems(members, "root"), [])
        self.assertEqual(members[3].mode, 0o755)
        self.assertEqual(members[2].mode, 0o644)

    def test_archive_member_problems(self):
        escape = build.tarfile.TarInfo("root/../evil")
        link = build.tarfile.TarInfo("root/link")
        link.type = build.tarfile.SYMTYPE
        outside = build.tarfile.TarInfo("other/file")
        problems = build.archive_member_problems([escape, link, outside], "root")
        self.assertEqual(len(problems), 3)


if __name__ == "__main__":
    unittest.main()
