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
        self.assertTrue(build.valid_release_tag("20261104-r2"))
        self.assertFalse(build.valid_release_tag("20269999"))

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
        parsed = build.parse_archive_name("ffmpeg-9.0.2+20261107-aarch64-unknown-linux-musl-runtime.tar.gz")
        self.assertEqual(parsed["profile"], "runtime")
        self.assertEqual(parsed["target"], "aarch64-unknown-linux-musl")


class LicenseAndDeviceTests(unittest.TestCase):
    def test_profile_licenses(self):
        expected = {"play-sdk": "lgpl", "tools": "gpl", "runtime": "gpl"}
        for name, license_name in expected.items():
            profile, _ = build.load_profile(name)
            self.assertEqual(profile["license"], license_name)
        self.assertEqual(build.FFMPEG_LICENSES["gpl"]["ffmpeg_license"], "GPL version 2 or later")
        self.assertEqual(build.FFMPEG_LICENSES["lgpl"]["ffmpeg_license"], "LGPL version 2.1 or later")

    def test_gpl_profiles_ship_the_gpl_text(self):
        self.assertIn("share/licenses/ffmpeg/COPYING.GPLv2", build.notice_paths("gpl"))
        self.assertNotIn("share/licenses/ffmpeg/COPYING.GPLv2", build.notice_paths("lgpl"))
        self.assertIn("share/licenses/ffmpeg/COPYING.LGPLv2.1", build.notice_paths("lgpl"))

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

    def test_stage_entries_keep_soname_links(self):
        self.write("lib/libavcodec.so.63.4.100", b"elf")
        for link, target in SONAME_CHAIN.items():
            self.link(link, target)
        files, links = build.stage_entries(self.stage)
        self.assertEqual(files, {"lib/libavcodec.so.63.4.100": (b"elf", False)})
        self.assertEqual(links, SONAME_CHAIN)

    def test_stage_entries_reject_unsafe_links(self):
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
                    build.stage_entries(self.stage)
                (self.stage / link).unlink()

    def test_stage_entries_reject_symlinked_directory(self):
        self.write("lib/real/libavcodec.so.63.4.100")
        self.link("lib/linked", "real")
        with self.assertRaises(SystemExit):
            build.stage_entries(self.stage)

    def test_archive_round_trips_soname_links(self):
        files = {"lib/libavcodec.so.63.4.100": (b"elf", True), "bin/ffmpeg": (b"exe", True)}
        first = self.root / "first.tar.gz"
        second = self.root / "second.tar.gz"
        build.write_deterministic_archive(first, "root", files, SONAME_CHAIN)
        build.write_deterministic_archive(second, "root", dict(reversed(list(files.items()))), dict(reversed(list(SONAME_CHAIN.items()))))
        self.assertEqual(first.read_bytes(), second.read_bytes())
        destination = self.root / "out"
        with build.tarfile.open(first) as archive:
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
        for relative in build.notice_paths("gpl"):
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
            "sha256": build.sha256_file(real),
        }
        libraries = {library: dict(entry) for library in build.RUNTIME_LIBRARIES}
        self.assertEqual(build.extracted_library_problems(self.stage, libraries, "linux"), [])
        libraries["libavcodec"]["sha256"] = "0" * 64
        libraries["libavutil"]["links"] = ["lib/libavutil.so"]
        problems = build.extracted_library_problems(self.stage, libraries, "linux")
        self.assertEqual(len(problems), 2, problems)


if __name__ == "__main__":
    unittest.main()
