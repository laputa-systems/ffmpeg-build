#!/usr/bin/env python3
"""Build, audit, and inspect the pinned FFmpeg profiles."""

import argparse
import hashlib
import json
import os
import pathlib
import platform
import re
import shlex
import shutil
import gzip
import io
import subprocess
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parent
WORK = ROOT / ".work"
CACHE = WORK / "cache" / "sources"
BUILD_ROOT = WORK / "build"
STAGE_ROOT = WORK / "stage"
TMP_ROOT = WORK / "tmp"
INSTALL_PREFIX = "/opt/ffmpeg-build"
MUSL_THREAD_STACK_BYTES = 2 * 1024 * 1024
DIST = ROOT / "dist"
LICENSE_FILES = {
    "ffmpeg": ("LICENSE.md", "COPYING.LGPLv2.1", "CREDITS"),
    "dav1d": ("COPYING",),
    "zlib": ("LICENSE",),
}
FFMPEG_LICENSE = "LGPL version 2.1 or later"
RELEASE_TAG = re.compile(r"(?:local|[0-9]{8}(?:-r[0-9]+)?)\Z")
ARCHIVE_NAME = re.compile(
    r"ffmpeg-(?P<upstream>[0-9]+(?:\.[0-9]+)*)\+(?P<tag>local|[0-9]{8}(?:-r[0-9]+)?)"
    r"-(?P<target>[a-z0-9_]+-[a-z0-9_]+-[a-z0-9_]+(?:-[a-z0-9_]+)?)-(?P<profile>play-sdk|tools)\.tar\.gz\Z"
)
MANIFEST_KEYS = (
    "contract",
    "profile",
    "target",
    "sources",
    "producer",
    "configure_args",
    "components",
    "auto_selected",
    "external_libraries",
    "bundled_dependencies",
    "frameworks",
    "system_libraries",
    "toolchain",
    "license",
)
ABSOLUTE_BUILD_TREE = re.compile(rb"[^.]/\.work/(?:build|stage)/")

COMPONENT_CATEGORIES = (
    "demuxers",
    "decoders",
    "subtitle_decoders",
    "encoders",
    "muxers",
    "parsers",
    "bsfs",
    "filters",
    "hwaccels",
    "protocols",
    "devices",
)

CONFIGURE_OPTION = {
    "demuxers": "--enable-demuxer",
    "decoders": "--enable-decoder",
    "subtitle_decoders": "--enable-decoder",
    "encoders": "--enable-encoder",
    "muxers": "--enable-muxer",
    "parsers": "--enable-parser",
    "bsfs": "--enable-bsf",
    "filters": "--enable-filter",
    "hwaccels": "--enable-hwaccel",
    "protocols": "--enable-protocol",
}

COMPONENT_ALIASES = {
    ("decoders", "mov_text"): "movtext",
    ("subtitle_decoders", "mov_text"): "movtext",
    ("encoders", "mov_text"): "movtext",
}

BUNDLED_LIBRARIES = {
    "dav1d": "libdav1d.a",
    "zlib": "libz.a",
}

NETWORK_PROTOCOLS = {
    "http",
    "https",
    "ftp",
    "sftp",
    "ssh",
    "rtsp",
    "rtsps",
    "rtmp",
    "rtmps",
    "rtmpt",
    "rtmpte",
    "rtmpts",
    "hls",
    "dash",
    "smb",
    "gopher",
    "gophers",
    "dav",
    "davs",
    "webdav",
    "webdavs",
    "mms",
    "mmsh",
    "mmst",
    "rtp",
    "srtp",
    "srt",
    "udp",
    "udplite",
    "tcp",
    "tls",
    "ipfs",
    "ipns",
    "sctp",
    "rist",
}


def fail(message):
    raise SystemExit(f"error: {message}")


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read {path}: {exc}")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command, cwd=None, env=None, capture=False, quiet=False):
    if not quiet:
        print("+ " + " ".join(shlex.quote(str(part)) for part in command))
    result = subprocess.run(
        [str(part) for part in command],
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=capture,
        check=False,
    )
    if result.returncode != 0:
        detail = ""
        if capture and result.stderr:
            detail = f"\n{result.stderr.strip()}"
        fail(f"command failed ({result.returncode}): {' '.join(map(str, command))}{detail}")
    return result


def output(command):
    return run(command, capture=True, quiet=True).stdout.strip()


def jobs():
    return max(1, os.cpu_count() or 1)


def load_sources():
    lock = read_json(ROOT / "sources.lock.json")
    if lock.get("contract") != 1:
        fail("sources.lock.json contract must be 1")
    sources = lock.get("sources")
    if not isinstance(sources, dict) or not sources:
        fail("sources.lock.json has no sources")
    for name, source in sources.items():
        for key in ("url", "sha256", "filename", "archive_root"):
            if not source.get(key):
                fail(f"source {name} lacks {key}")
        if not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]):
            fail(f"source {name} has an invalid sha256")
    return lock


ARTIFACTS = ("sdk", "tools")
TOOLS_PROGRAMS = ("ffmpeg", "ffprobe")


def load_profile(name):
    path = ROOT / "profiles" / f"{name}.json"
    profile = read_json(path)
    if profile.get("profile") != name:
        fail(f"{path} does not declare profile {name}")
    if profile.get("artifact") not in ARTIFACTS:
        fail(f"{path} artifact must be one of {ARTIFACTS}")
    targets = profile.get("targets")
    if not isinstance(targets, dict) or not targets:
        fail(f"{path} has no target scope")
    return profile, path


def target_config(profile, target):
    if target not in profile["targets"]:
        fail(f"target {target} is not in profile {profile['profile']}")
    config = profile["targets"][target]
    if not config.get("platform"):
        fail(f"target {target} lacks a platform")
    if not config.get("arch"):
        fail(f"target {target} lacks an architecture")
    return config


def dedupe(values):
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def merged_components(profile, target):
    target_values = target_config(profile, target)
    merged = {}
    for layer in (profile.get("components", {}), target_values.get("components", {})):
        for category, names in layer.items():
            if category not in COMPONENT_CATEGORIES:
                fail(f"unknown component category {category}")
            if not isinstance(names, list):
                fail(f"component category {category} must be a list")
            merged.setdefault(category, [])
            merged[category].extend(names)
    return {category: dedupe(names) for category, names in merged.items() if names}


def requested_components(profile, target):
    merged = merged_components(profile, target)
    if merged.get("devices"):
        fail("producer profiles cannot request devices")
    requested = {}
    for category in COMPONENT_CATEGORIES:
        if category == "subtitle_decoders":
            if merged.get(category):
                requested.setdefault("decoders", []).extend(merged[category])
        elif category == "devices":
            continue
        elif merged.get(category):
            requested[category] = list(merged[category])
    if requested.get("decoders"):
        requested["decoders"] = dedupe(requested["decoders"])
    return requested


def configure_component(category, name):
    return COMPONENT_ALIASES.get((category, name), name)


HOST_PLATFORMS = {
    ("Darwin", "arm64"): ("macos", "aarch64"),
    ("Linux", "x86_64"): ("linux", "x86_64"),
    ("Linux", "aarch64"): ("linux", "aarch64"),
}


def require_native_host(config, target):
    host = HOST_PLATFORMS.get((platform.system(), platform.machine()))
    wanted = (config["platform"], config["arch"])
    if host != wanted:
        fail(
            f"target {target} builds natively on {wanted[0]} {wanted[1]}; "
            f"this host is {platform.system()} {platform.machine()}"
            + ("; use scripts/linux-build.sh" if wanted[0] == "linux" else "")
        )


def musl_version():
    result = subprocess.run(["ldd", "--version"], capture_output=True, text=True, check=False)
    text = result.stdout + result.stderr
    if "musl" not in text:
        fail("Linux targets require a musl host; ldd does not report musl")
    match = re.search(r"Version ([0-9][0-9.]*)", text)
    if not match:
        fail("cannot read the musl version from ldd")
    return match.group(1)


def platform_toolchain(config):
    info = {
        "host": platform.platform(),
        "cpu_baseline": config.get("cpu_baseline", ""),
        "deployment_target": config.get("deployment_target", ""),
    }
    cc = config.get("cc", "cc")
    info["cc"] = output([cc, "--version"]).splitlines()[0]
    if config["platform"] == "macos":
        info["sdk"] = output(["xcrun", "--sdk", "macosx", "--show-sdk-path"])
        info["sdk_version"] = output(["xcrun", "--sdk", "macosx", "--show-sdk-version"])
        info["sysroot"] = info["sdk"]
    else:
        os_release = pathlib.Path("/etc/alpine-release")
        info["sdk"] = "alpine"
        info["sdk_version"] = os_release.read_text().strip() if os_release.is_file() else ""
        info["sysroot"] = output([cc, "-print-sysroot"]) or "/"
        info["libc"] = f"musl {musl_version()}"
    return info


def build_paths(profile_name, target):
    profile, _ = load_profile(profile_name)
    stage = STAGE_ROOT / target / profile_name
    build_dir = BUILD_ROOT / target / profile_name
    deps = stage if profile["artifact"] == "sdk" else build_dir / "deps"
    return stage, build_dir, deps


def configure_args_for(profile, target, build_dir, deps, toolchain):
    config = target_config(profile, target)
    requested = requested_components(profile, target)
    cc = config.get("cc", "cc")
    programs = ["--disable-programs"]
    if profile["artifact"] == "tools":
        programs += [f"--enable-{name}" for name in TOOLS_PROGRAMS]
        programs.append("--pkg-config-flags=--static")
    args = [
        f"--prefix={INSTALL_PREFIX}",
        "--disable-shared",
        "--enable-static",
        *programs,
        "--disable-doc",
        "--disable-network",
        "--disable-avdevice",
        "--disable-autodetect",
        "--disable-everything",
        "--enable-libdav1d",
        "--enable-zlib",
        "--enable-pic",
        f"--cc={cc}",
    ]
    extra_cflags = ["-O2", "-fPIC"]
    extra_ldflags = []
    if config["platform"] == "macos":
        args.append(f"--sysroot={toolchain['sysroot']}")
        target_version = config.get("deployment_target")
        if not target_version:
            fail(f"macOS target {target} lacks deployment_target")
        extra_cflags.append(f"-mmacosx-version-min={target_version}")
        extra_ldflags.append(f"-mmacosx-version-min={target_version}")
    else:
        args.append(f"--arch={config['arch']}")
        extra_cflags.append(f"-march={config['cpu_baseline']}")
    relative_deps = os.path.relpath(deps, build_dir / "ffmpeg")
    extra_cflags.append(f"-I{relative_deps}/include")
    extra_ldflags.append(f"-L{relative_deps}/lib")
    args.append("--extra-cflags=" + " ".join(extra_cflags))
    args.append("--extra-ldflags=" + " ".join(extra_ldflags))
    if profile["artifact"] == "tools" and config["platform"] == "linux":
        args.append(f"--extra-ldexeflags=-static-pie -Wl,-z,stack-size={MUSL_THREAD_STACK_BYTES}")
    args.extend(config.get("configure_flags", []))
    for category, names in requested.items():
        option = CONFIGURE_OPTION[category]
        for name in names:
            args.append(f"{option}={configure_component(category, name)}")
    return args


def dep_env(config, deps, toolchain):
    env = os.environ.copy()
    env["TMPDIR"] = str(TMP_ROOT)
    env["CC"] = config.get("cc", "cc")
    env["PKG_CONFIG_PATH"] = str(deps / "lib" / "pkgconfig")
    env["PKG_CONFIG_LIBDIR"] = str(deps / "lib" / "pkgconfig")
    cflags = ["-O2", "-fPIC", prefix_map_flag()]
    ldflags = []
    if config["platform"] == "macos":
        cflags.extend(["-isysroot", toolchain["sdk"]])
        cflags.append(f"-mmacosx-version-min={config['deployment_target']}")
        ldflags.extend(["-isysroot", toolchain["sdk"]])
        ldflags.append(f"-mmacosx-version-min={config['deployment_target']}")
        env["MACOSX_DEPLOYMENT_TARGET"] = config["deployment_target"]
    else:
        cflags.append(f"-march={config['cpu_baseline']}")
    env["CFLAGS"] = " ".join(cflags)
    env["CXXFLAGS"] = env["CFLAGS"]
    env["LDFLAGS"] = " ".join(ldflags)
    return env


SYSTEM_PKG_CONFIG_DIRS = ("/usr/lib/pkgconfig", "/usr/share/pkgconfig")


def prefix_map_flag():
    return f"-ffile-prefix-map={ROOT}=."


def ffmpeg_env(config, deps):
    env = os.environ.copy()
    env["TMPDIR"] = str(TMP_ROOT)
    for variable in ("CFLAGS", "ASFLAGS", "OBJCFLAGS"):
        env[variable] = prefix_map_flag()
    search = [str(deps / "lib" / "pkgconfig")]
    if config.get("system_libraries"):
        search.extend(SYSTEM_PKG_CONFIG_DIRS)
    env["PKG_CONFIG_PATH"] = search[0]
    env["PKG_CONFIG_LIBDIR"] = os.pathsep.join(search)
    return env


def fetch_source(name, source):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / source["filename"]
    if path.exists():
        digest = sha256_file(path)
        if digest == source["sha256"]:
            print(f"cached {name} {source['version']} sha256 {digest}")
            return path
        print(f"cached {name} has the wrong sha256; discarding {path.name}")
        path.unlink()
    print(f"download {name} {source['version']} from {source['url']}")
    part = path.with_name(path.name + ".part")
    try:
        run(["curl", "-fsSL", source["url"], "-o", str(part)])
        digest = sha256_file(part)
        if digest != source["sha256"]:
            fail(f"checksum mismatch for {name}: got {digest}, expected {source['sha256']}")
        part.replace(path)
    finally:
        if part.exists():
            part.unlink()
    print(f"verified {name} sha256 {source['sha256']}")
    return path


def fetch_profile_sources(profile, lock):
    names = profile.get("sources")
    if not isinstance(names, list) or not names:
        fail(f"profile {profile['profile']} has no sources")
    for name in names:
        if name not in lock["sources"]:
            fail(f"profile {profile['profile']} references unknown source {name}")
        fetch_source(name, lock["sources"][name])


def extract_source(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    run(["tar", "-xf", str(CACHE / source["filename"]), "-C", str(destination)])
    root = destination / source["archive_root"]
    if not root.is_dir():
        fail(f"archive {source['filename']} did not contain {source['archive_root']}")
    return root


def build_zlib(source_dir, prefix, env):
    run(["./configure", f"--prefix={prefix}", "--static"], cwd=source_dir, env=env)
    run(["make", f"-j{jobs()}"], cwd=source_dir, env=env)
    run(["make", "install"], cwd=source_dir, env=env)


def build_dav1d(source_dir, build_dir, prefix, env):
    if build_dir.exists():
        shutil.rmtree(build_dir)
    run(
        [
            "meson",
            "setup",
            str(build_dir),
            str(source_dir),
            f"--prefix={prefix}",
            "--libdir=lib",
            "--buildtype=release",
            "--default-library=static",
            "-Denable_tools=false",
            "-Denable_tests=false",
        ],
        env=env,
    )
    run(["ninja", "-C", str(build_dir), "install"], env=env)


def normalize_pc(stage):
    pc_dir = stage / "lib" / "pkgconfig"
    if not pc_dir.is_dir():
        fail(f"no pkg-config directory in {stage}")
    stage_prefix = "${pcfiledir}/../.."
    for pc in sorted(pc_dir.glob("*.pc")):
        text = pc.read_text()
        text = text.replace(str(stage), stage_prefix).replace(INSTALL_PREFIX, stage_prefix)
        lines = []
        for line in text.splitlines():
            if line.startswith("prefix="):
                lines.append(f"prefix={stage_prefix}")
            elif line.startswith("exec_prefix="):
                lines.append("exec_prefix=${prefix}")
            elif line.startswith("libdir="):
                lines.append("libdir=${prefix}/lib")
            elif line.startswith("includedir="):
                lines.append("includedir=${prefix}/include")
            elif line.startswith("sharedlibdir="):
                lines.append("sharedlibdir=${libdir}")
            else:
                lines.append(line)
        pc.write_text("\n".join(lines) + "\n")


def prune_stage(stage, artifact):
    trees = ["share/man", "share/ffmpeg", "share/doc", "share/examples"]
    files = []
    if artifact == "sdk":
        files += [f"bin/{name}" for name in (*TOOLS_PROGRAMS, "ffplay")]
    else:
        trees += ["include", "lib"]
    for relative in trees:
        path = stage / relative
        if path.exists():
            shutil.rmtree(path)
    for relative in files:
        path = stage / relative
        if path.exists():
            path.unlink()
    bin_dir = stage / "bin"
    if bin_dir.is_dir() and not any(bin_dir.iterdir()):
        bin_dir.rmdir()


def parse_components(build_dir):
    path = build_dir / "config_components.h"
    if not path.is_file():
        fail(f"missing {path}")
    kind_map = {
        "DECODER": "decoders",
        "DEMUXER": "demuxers",
        "PARSER": "parsers",
        "BSF": "bsfs",
        "FILTER": "filters",
        "HWACCEL": "hwaccels",
        "PROTOCOL": "protocols",
        "ENCODER": "encoders",
        "MUXER": "muxers",
        "DEVICE": "devices",
        "INDEV": "devices",
        "OUTDEV": "devices",
    }
    pattern = re.compile(
        r"^#define CONFIG_(\w+)_(DECODER|DEMUXER|PARSER|BSF|FILTER|HWACCEL|"
        r"PROTOCOL|ENCODER|MUXER|DEVICE|INDEV|OUTDEV) 1$"
    )
    components = {}
    for line in path.read_text().splitlines():
        match = pattern.match(line)
        if not match:
            continue
        name, kind = match.groups()
        components.setdefault(kind_map[kind], set()).add(name.lower())
    return {category: sorted(names) for category, names in components.items()}


def parse_config_mak(build_dir):
    path = build_dir / "ffbuild" / "config.mak"
    if not path.is_file():
        fail(f"missing {path}")
    return path.read_text()


def parse_external_libraries(config_mak):
    libraries = set()
    for line in config_mak.splitlines():
        match = re.match(r"^CONFIG_LIB([A-Z0-9_]+)=yes$", line)
        if not match:
            continue
        name = match.group(1).lower()
        if name.endswith(
            ("_decoder", "_encoder", "_parser", "_bsf", "_filter", "_demuxer",
             "_muxer", "_hwaccel", "_protocol")
        ):
            continue
        libraries.add(name[3:] if name.startswith("lib") else name)
    return sorted(libraries)


def parse_configuration(config_mak):
    for line in config_mak.splitlines():
        if line.startswith("FFMPEG_CONFIGURATION="):
            return line.split("=", 1)[1]
    return ""


def auto_selected(requested, resolved):
    selected = {}
    for category, names in resolved.items():
        wanted = {configure_component(category, name) for name in requested.get(category, [])}
        extra = sorted(set(names) - wanted)
        if extra:
            selected[category] = extra
    return selected


def component_problems(requested, resolved):
    problems = []
    for category in ("encoders", "muxers", "devices"):
        names = set(resolved.get(category, []))
        if names:
            problems.append(f"{category} enabled: {sorted(names)}")
    protocols = set(resolved.get("protocols", []))
    allowed = set(requested.get("protocols", []))
    extra = protocols - allowed
    if extra:
        problems.append(f"protocols outside profile: {sorted(extra)}")
    network = protocols & NETWORK_PROTOCOLS
    if network:
        problems.append(f"network protocols enabled: {sorted(network)}")
    for category, names in requested.items():
        wanted = {configure_component(category, name) for name in names}
        missing = wanted - set(resolved.get(category, []))
        if missing:
            problems.append(f"missing {category}: {sorted(missing)}")
    return problems


def build_fingerprint(profile_path, target, profile_name, args, toolchain):
    digest = hashlib.sha256()
    for path in (ROOT / "build.py", ROOT / "sources.lock.json", profile_path):
        digest.update(path.read_bytes())
    digest.update(
        json.dumps(
            {
                "target": target,
                "profile": profile_name,
                "configure_args": args,
                "toolchain": toolchain,
                "python": sys.version,
                "machine": platform.machine(),
                "system": platform.system(),
            },
            sort_keys=True,
        ).encode()
    )
    return digest.hexdigest()


def finish_programs(config, stage):
    for name in TOOLS_PROGRAMS:
        binary = stage / "bin" / name
        if config["platform"] == "macos":
            run(["strip", str(binary)])
            run(["codesign", "--force", "--sign", "-", str(binary)])
        else:
            run(["strip", "--strip-all", str(binary)])


def notice_paths():
    paths = ["README"]
    for name, files in LICENSE_FILES.items():
        paths.extend(f"share/licenses/{name}/{filename}" for filename in files)
    return paths


def stage_complete(stage, artifact):
    if not all((stage / path).is_file() for path in notice_paths()):
        return False
    if artifact == "tools":
        required = (*(f"bin/{name}" for name in TOOLS_PROGRAMS), "share/ffmpeg-build/manifest.json")
        return all((stage / path).is_file() for path in required)
    required = (
        "include/libavutil/ffversion.h",
        "lib/libavcodec.a",
        "lib/libavformat.a",
        "lib/libavfilter.a",
        "lib/libavutil.a",
        "lib/libswresample.a",
        "lib/libswscale.a",
        "lib/libdav1d.a",
        "lib/libz.a",
        "lib/pkgconfig/libavcodec.pc",
        "lib/pkgconfig/libavfilter.pc",
        "lib/pkgconfig/libavformat.pc",
        "lib/pkgconfig/libavutil.pc",
        "lib/pkgconfig/libswresample.pc",
        "lib/pkgconfig/libswscale.pc",
        "lib/pkgconfig/dav1d.pc",
        "lib/pkgconfig/zlib.pc",
        "include/dav1d/dav1d.h",
        "include/zlib.h",
        "share/ffmpeg-build/manifest.json",
    )
    return all((stage / path).is_file() for path in required)


def git_commit():
    try:
        return output(["git", "-C", str(ROOT), "rev-parse", "HEAD"])
    except SystemExit:
        return "unknown"


def manifest_for(profile, target, build_dir, stage, args, toolchain):
    config = target_config(profile, target)
    requested = requested_components(profile, target)
    resolved = parse_components(build_dir)
    config_mak = parse_config_mak(build_dir)
    sources = {}
    lock = load_sources()
    for name in profile["sources"]:
        source = lock["sources"][name]
        sources[name] = {
            "version": source["version"],
            "sha256": source["sha256"],
            "url": source["url"],
        }
    return {
        "contract": 1,
        "profile": profile["profile"],
        "target": target,
        "sources": sources,
        "producer": {
            "repository": "laputa-systems/ffmpeg-build",
            "commit": git_commit(),
        },
        "configure_args": args,
        "configure": parse_configuration(config_mak),
        "components": resolved,
        "requested_components": requested,
        "auto_selected": auto_selected(requested, resolved),
        "external_libraries": parse_external_libraries(config_mak),
        "bundled_dependencies": config.get("bundled_dependencies", []),
        "frameworks": config.get("frameworks", []),
        "system_libraries": config.get("system_libraries", []),
        "toolchain": toolchain,
        "license": parse_license(build_dir),
    }


def parse_license(ffmpeg_build):
    match = re.search(r'#define FFMPEG_LICENSE "([^"]+)"', (ffmpeg_build / "config.h").read_text())
    if not match:
        fail(f"no FFMPEG_LICENSE in {ffmpeg_build / 'config.h'}")
    return match.group(1)


def install_notices(profile, target, sources, stage):
    for name, files in LICENSE_FILES.items():
        destination = stage / "share" / "licenses" / name
        destination.mkdir(parents=True, exist_ok=True)
        for filename in files:
            shutil.copyfile(sources[name] / filename, destination / filename)
    if profile["artifact"] == "sdk":
        contents = (
            "include/            FFmpeg, dav1d, and zlib headers\n"
            "lib/*.a             static FFmpeg libraries, libdav1d.a, libz.a\n"
            "lib/pkgconfig/      relocatable pkg-config files; use pkg-config --static\n"
        )
    else:
        contents = "bin/ffmpeg, bin/ffprobe   static, headless; no network protocols or devices\n"
    (stage / "README").write_text(
        f"FFmpeg {profile['profile']} for {target}\n"
        "Built by https://github.com/laputa-systems/ffmpeg-build from pinned upstream sources.\n\n"
        + contents
        + "share/ffmpeg-build/manifest.json   sources, configuration, components, toolchain\n"
        "share/licenses/     upstream licenses and notices for FFmpeg, dav1d, and zlib\n"
    )


def write_manifest(stage, manifest):
    path = stage / "share" / "ffmpeg-build" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path}")


def build(target, profile_name):
    lock = load_sources()
    profile, profile_path = load_profile(profile_name)
    config = target_config(profile, target)
    require_native_host(config, target)
    artifact = profile["artifact"]
    stage, build_dir, deps = build_paths(profile_name, target)
    toolchain = platform_toolchain(config)
    args = configure_args_for(profile, target, build_dir, deps, toolchain)
    fingerprint = build_fingerprint(profile_path, target, profile_name, args, toolchain)
    stamp_path = build_dir / "stamp.json"
    if stamp_path.is_file() and stage_complete(stage, artifact):
        stamp = read_json(stamp_path)
        if stamp.get("fingerprint") == fingerprint:
            print(f"up to date: {stage}")
            return

    fetch_profile_sources(profile, lock)
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    if build_dir.exists():
        shutil.rmtree(build_dir)
    if stage.exists():
        shutil.rmtree(stage)
    build_dir.mkdir(parents=True)
    stage.mkdir(parents=True)

    source_root = build_dir / "src"
    ffmpeg_source = extract_source(lock["sources"]["ffmpeg"], source_root)
    zlib_source = extract_source(lock["sources"]["zlib"], source_root)
    dav1d_source = extract_source(lock["sources"]["dav1d"], source_root)
    (ffmpeg_source / "VERSION").write_text(lock["sources"]["ffmpeg"]["version"] + "\n")

    env = dep_env(config, deps, toolchain)
    print(f"build zlib {lock['sources']['zlib']['version']}")
    build_zlib(zlib_source, deps, env)
    print(f"build dav1d {lock['sources']['dav1d']['version']}")
    build_dav1d(dav1d_source, build_dir / "dav1d", deps, env)

    ffmpeg_build = build_dir / "ffmpeg"
    ffmpeg_build.mkdir()
    print(f"configure FFmpeg {lock['sources']['ffmpeg']['version']}")
    run([str(ffmpeg_source / "configure"), *args], cwd=ffmpeg_build, env=ffmpeg_env(config, deps))
    print(f"build FFmpeg {lock['sources']['ffmpeg']['version']}")
    run(["make", f"-j{jobs()}"], cwd=ffmpeg_build, env=ffmpeg_env(config, deps))
    install_root = build_dir / "install"
    run(["make", "install", f"DESTDIR={install_root}"], cwd=ffmpeg_build, env=ffmpeg_env(config, deps))
    shutil.copytree(install_root / INSTALL_PREFIX.lstrip("/"), stage, symlinks=True, dirs_exist_ok=True)
    shutil.rmtree(install_root)

    prune_stage(stage, artifact)
    install_notices(
        profile,
        target,
        {"ffmpeg": ffmpeg_source, "dav1d": dav1d_source, "zlib": zlib_source},
        stage,
    )
    if artifact == "tools":
        finish_programs(config, stage)
    if artifact == "sdk":
        normalize_pc(stage)
    manifest = manifest_for(profile, target, ffmpeg_build, stage, args, toolchain)
    write_manifest(stage, manifest)
    if not stage_complete(stage, artifact):
        fail(f"stage is incomplete after build: {stage}")
    stamp = {
        "fingerprint": fingerprint,
        "target": target,
        "profile": profile_name,
        "sources": {
            name: {
                "version": lock["sources"][name]["version"],
                "sha256": lock["sources"][name]["sha256"],
            }
            for name in profile["sources"]
        },
        "profile_sha256": sha256_file(profile_path),
        "build_py_sha256": sha256_file(ROOT / "build.py"),
        "flags": args,
        "toolchain": toolchain,
    }
    stamp_path.write_text(json.dumps(stamp, indent=2, sort_keys=True) + "\n")
    print(f"staged {stage}")


ELF_MACHINE = {
    "x86_64": "x86-64",
    "aarch64": "ARM aarch64",
}

FFMPEG_ARCH_DEFINE = {
    "x86_64": "ARCH_X86_64",
    "aarch64": "ARCH_AARCH64",
}

HOST_CPU_FLAGS = re.compile(r"-m(?:arch|cpu|tune)=native\b")


COMPILE_FLAG_VARIABLES = re.compile(r"^(?:CPPFLAGS|CFLAGS|CXXFLAGS|ASFLAGS|LDFLAGS|LDEXEFLAGS)=(.*)$", re.M)


def host_cpu_flag_problems(config_mak, arch):
    flags = " ".join(COMPILE_FLAG_VARIABLES.findall(config_mak))
    problems = []
    if HOST_CPU_FLAGS.search(flags):
        problems.append("host-specific -march/-mcpu/-mtune=native")
    if arch == "aarch64" and re.search(r"-m(?:sse|avx|mmx|64\b)", flags):
        problems.append("x86 code-generation flag on aarch64")
    return problems


def pc_declares(pc_texts, library):
    flag = "-l" + library.removeprefix("lib")
    for text in pc_texts:
        for line in text.splitlines():
            key = line.split(":", 1)[0]
            if key in ("Requires", "Requires.private") and re.search(
                rf"(?:^|[\s,:]){re.escape(library)}(?:[\s,]|$)", line
            ):
                return True
            if key in ("Libs", "Libs.private") and re.search(
                rf"(?:^|\s){re.escape(flag)}(?:\s|$)", line
            ):
                return True
    return False


class Audit:
    def __init__(self):
        self.results = []

    def case(self, name, ok, detail=""):
        status = "PASS" if ok else "FAIL"
        line = f"{status} audit: {name}"
        if detail and not ok:
            line += f": {detail}"
        print(line)
        self.results.append(bool(ok))

    def finish(self):
        passed = sum(1 for result in self.results if result)
        failed = len(self.results) - passed
        print(f"TOTAL {passed} passed, {failed} failed")
        return 0 if failed == 0 else 1


def read_manifest(check, stage):
    path = stage / "share" / "ffmpeg-build" / "manifest.json"
    if not path.is_file():
        check.case("manifest readable", False, f"missing {path}")
        return {}
    try:
        manifest = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        check.case("manifest readable", False, str(exc))
        return {}
    check.case("manifest readable", True)
    return manifest


def audit(target, profile_name):
    lock = load_sources()
    profile, _ = load_profile(profile_name)
    config = target_config(profile, target)
    require_native_host(config, target)
    artifact = profile["artifact"]
    stage, build_dir, deps = build_paths(profile_name, target)
    check = Audit()
    case = check.case

    if not build_dir.is_dir():
        fail(f"missing build tree {build_dir}; run build first")
    if not stage.is_dir():
        fail(f"missing stage {stage}; run build first")

    ffmpeg_build = build_dir / "ffmpeg"
    resolved = parse_components(ffmpeg_build)
    config_mak = parse_config_mak(ffmpeg_build)
    requested = requested_components(profile, target)
    args = configure_args_for(profile, target, build_dir, deps, platform_toolchain(config))
    configuration = parse_configuration(config_mak)
    external_libraries = parse_external_libraries(config_mak)
    selected = auto_selected(requested, resolved)

    case("no devices", not resolved.get("devices"), f"devices: {resolved.get('devices')}")
    if artifact == "sdk":
        for category in ("encoders", "muxers"):
            names = resolved.get(category, [])
            case(f"no {category}", not names, f"{category}: {names}")
    else:
        for category in ("encoders", "muxers"):
            extra = selected.get(category, [])
            case(f"no unrequested {category}", not extra, f"{category}: {extra}")
        case("no hardware decode", not resolved.get("hwaccels"), f"hwaccels: {resolved.get('hwaccels')}")

    protocols = set(resolved.get("protocols", []))
    allowed_protocols = set(requested.get("protocols", []))
    case(
        "protocols allowed",
        protocols <= allowed_protocols,
        f"extra: {sorted(protocols - allowed_protocols)}",
    )
    case(
        "no network protocols",
        not (protocols & NETWORK_PROTOCOLS),
        f"network: {sorted(protocols & NETWORK_PROTOCOLS)}",
    )
    case(
        "network disabled in configure",
        "--disable-network" in configuration,
        "configuration lacks --disable-network",
    )

    for category, names in requested.items():
        wanted = {configure_component(category, name) for name in names}
        missing = sorted(wanted - set(resolved.get(category, [])))
        case(f"requested {category} present", not missing, f"missing: {missing}")
    print(f"auto-selected: {json.dumps(selected, sort_keys=True)}")

    manifest = read_manifest(check, stage)
    if manifest:
        case("manifest contract", manifest.get("contract") == 1)
        case("manifest producer", bool(manifest.get("producer", {}).get("commit")))
        case(
            "manifest profile and target",
            manifest.get("profile") == profile_name and manifest.get("target") == target,
        )
        case(
            "manifest sources",
            all(
                manifest.get("sources", {}).get(name, {}).get("sha256")
                == lock["sources"][name]["sha256"]
                for name in profile["sources"]
            ),
        )
        case("manifest components match build tree", manifest.get("components") == resolved)
        case("manifest auto-selected match build tree", manifest.get("auto_selected") == selected)
        case("manifest external libraries", manifest.get("external_libraries") == external_libraries)
        case(
            "manifest bundled dependencies",
            manifest.get("bundled_dependencies") == config.get("bundled_dependencies", []),
        )
        case("manifest frameworks", manifest.get("frameworks") == config.get("frameworks", []))
        case(
            "manifest system libraries",
            manifest.get("system_libraries") == config.get("system_libraries", []),
        )
        toolchain = manifest.get("toolchain", {})
        case(
            "manifest toolchain",
            bool(toolchain.get("cc"))
            and bool(toolchain.get("sysroot"))
            and bool(toolchain.get("cpu_baseline")),
            f"toolchain: {toolchain}",
        )
        if config["platform"] == "linux":
            case(
                "manifest libc is musl",
                toolchain.get("libc", "").startswith("musl "),
                f"libc: {toolchain.get('libc')!r}",
            )
        case("manifest configure arguments", manifest.get("configure_args") == args)
        case("manifest effective configure", manifest.get("configure") == configuration)
        case("manifest license", manifest.get("license") == FFMPEG_LICENSE, f"license: {manifest.get('license')!r}")

    case(
        "external libraries allowed",
        set(external_libraries) <= set(config.get("external_libraries", [])),
        f"extra: {sorted(set(external_libraries) - set(config.get('external_libraries', [])))}",
    )
    case("zlib enabled", "CONFIG_ZLIB=yes" in config_mak)
    case(
        "PIC enabled",
        "--enable-pic" in args and re.search(r"-fPIC\b|-fpic\b", config_mak) is not None,
    )
    case("no LTO flags", "-flto" not in config_mak)
    if config["platform"] == "linux":
        audit_linux_config(case, config, ffmpeg_build, config_mak)

    missing_notices = [path for path in notice_paths() if not (stage / path).is_file()]
    case("README and licenses present", not missing_notices, f"missing: {missing_notices}")
    case("no GPL or nonfree code", not re.search(r"^CONFIG_(?:GPL|NONFREE|VERSION3)=yes$", config_mak, re.M))

    leaked = build_prefix_leaks(stage)
    case("no absolute build prefix in artifact", not leaked, f"files: {leaked[:10]}")

    version = lock["sources"]["ffmpeg"]["version"]
    if artifact == "sdk":
        audit_sdk(case, target, profile_name, config, stage, version)
    else:
        audit_tools(case, config, stage, version)
    return check.finish()


def build_prefix_leaks(stage):
    needle = (str(ROOT) + "/").encode()
    return sorted(
        str(path.relative_to(stage))
        for path in stage.rglob("*")
        if path.is_file() and not path.is_symlink() and needle in path.read_bytes()
    )


def audit_linux_config(case, config, ffmpeg_build, config_mak):
    arch = config["arch"]
    config_h = (ffmpeg_build / "config.h").read_text()
    case(
        f"FFmpeg configured for {arch}",
        f"#define {FFMPEG_ARCH_DEFINE[arch]} 1" in config_h,
    )
    problems = host_cpu_flag_problems(config_mak, arch)
    case("no host-specific CPU flags", not problems, "; ".join(problems))
    case(
        f"CPU baseline -march={config['cpu_baseline']}",
        f"-march={config['cpu_baseline']}" in " ".join(COMPILE_FLAG_VARIABLES.findall(config_mak)),
    )


def audit_sdk(case, target, profile_name, config, stage, version):
    ffversion_path = stage / "include" / "libavutil" / "ffversion.h"
    ffversion = ""
    if ffversion_path.is_file():
        match = re.search(r'#define FFMPEG_VERSION "([^"]+)"', ffversion_path.read_text())
        if match:
            ffversion = match.group(1)
    case(f"ffversion is {version}", ffversion == version, f"found {ffversion!r}")

    programs = []
    if (stage / "bin").is_dir():
        programs = sorted(path.name for path in (stage / "bin").iterdir())
    case("no programs installed", not programs, f"programs: {programs}")

    headers = (
        "include/libavcodec/avcodec.h",
        "include/libavformat/avformat.h",
        "include/libavfilter/avfilter.h",
        "include/libavutil/avutil.h",
        "include/libswresample/swresample.h",
        "include/libswscale/swscale.h",
        "include/dav1d/dav1d.h",
        "include/zlib.h",
    )
    missing_headers = [path for path in headers if not (stage / path).is_file()]
    case("headers present", not missing_headers, f"missing: {missing_headers}")

    for dependency in config.get("bundled_dependencies", []):
        library = BUNDLED_LIBRARIES.get(dependency)
        if not library:
            case(f"bundled dependency {dependency}", False, "unknown bundled dependency")
            continue
        case(f"bundled {dependency} archive", (stage / "lib" / library).is_file())

    pc_files = sorted((stage / "lib" / "pkgconfig").glob("*.pc"))
    case("pkg-config files present", bool(pc_files), f"found {len(pc_files)}")
    for pc in pc_files:
        text = pc.read_text()
        prefix = next((line for line in text.splitlines() if line.startswith("prefix=")), "")
        leaked = str(stage) in text or str(ROOT) in text
        case(
            f"{pc.name} relocatable",
            "${pcfiledir}" in prefix and not leaked,
            f"prefix={prefix!r} leaked={leaked}",
        )

    archive_problems = []
    archives = sorted((stage / "lib").glob("*.a"))
    case("static archives present", bool(archives), f"found {len(archives)}")
    for archive in archives:
        work = TMP_ROOT / f"audit-{target}-{profile_name}-{archive.name}"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        try:
            run(["ar", "x", str(archive)], cwd=work, quiet=True)
            objects = sorted(
                path
                for path in work.rglob("*")
                if path.is_file() and path.suffix in {".o", ".obj"}
            )
            if not objects:
                archive_problems.append(f"{archive.name}: no objects")
                continue
            kinds = run(["file", "-b", *map(str, objects)], capture=True, quiet=True).stdout
            for line in kinds.splitlines():
                problem = object_kind_problem(config, line)
                if problem:
                    archive_problems.append(f"{archive.name}: {problem}")
                    break
        finally:
            if work.exists():
                shutil.rmtree(work)
    case(
        "archives contain object code, not bitcode",
        not archive_problems,
        "; ".join(archive_problems[:5]),
    )

    if config["platform"] == "linux":
        glibc = [archive.name for archive in archives if b"GLIBC_" in archive.read_bytes()]
        case("no glibc symbol versions", not glibc, f"archives: {glibc}")
        pc_texts = [pc.read_text() for pc in sorted((stage / "lib" / "pkgconfig").glob("libav*.pc"))]
        for library in config.get("system_libraries", []):
            case(f"pkg-config declares {library}", pc_declares(pc_texts, library))
        print(
            "abi: static archives for musl; no symbol versioning; "
            f"system libraries linked by the consumer: {config.get('system_libraries', [])}"
        )


def object_kind_problem(config, line):
    if "bitcode" in line.lower():
        return "LTO bitcode"
    if config["platform"] == "macos" and "Mach-O" not in line:
        return line
    if config["platform"] == "linux" and ("ELF" not in line or ELF_MACHINE[config["arch"]] not in line):
        return line
    return None


MACOS_SYSTEM_LIBRARY = re.compile(r"^(?:/usr/lib/|/System/Library/Frameworks/)")


def macos_linked_libraries(binary):
    lines = output(["otool", "-L", str(binary)]).splitlines()[1:]
    return [line.strip().split(" (", 1)[0] for line in lines if line.strip()]


def gnu_stack_size(program_headers):
    for line in program_headers.splitlines():
        fields = line.split()
        if fields and fields[0] == "GNU_STACK":
            return int(fields[5], 16)
    return None


def audit_tools(case, config, stage, version):
    bin_dir = stage / "bin"
    programs = sorted(path.name for path in bin_dir.iterdir()) if bin_dir.is_dir() else []
    case("programs are ffmpeg and ffprobe", programs == sorted(TOOLS_PROGRAMS), f"programs: {programs}")
    for relative in ("include", "lib"):
        case(f"no {relative}/ in tools stage", not (stage / relative).exists())

    for name in TOOLS_PROGRAMS:
        binary = bin_dir / name
        if not binary.is_file():
            case(f"{name} present", False)
            continue
        result = subprocess.run([str(binary), "-hide_banner", "-version"], capture_output=True, text=True, check=False)
        first = result.stdout.splitlines()[0] if result.stdout else ""
        case(f"{name} reports {version}", first.startswith(f"{name} version {version} "), f"found {first!r}")
        buildconf = subprocess.run([str(binary), "-hide_banner", "-buildconf"], capture_output=True, text=True, check=False).stdout
        case(f"{name} -buildconf has --disable-network", "--disable-network" in buildconf)
        data = binary.read_bytes()
        kind = output(["file", "-b", str(binary)])
        if config["platform"] == "macos":
            case(f"{name} is Mach-O arm64", "Mach-O 64-bit executable arm64" in kind, kind)
            libraries = macos_linked_libraries(binary)
            foreign = [library for library in libraries if not MACOS_SYSTEM_LIBRARY.match(library)]
            case(f"{name} links only system libraries", not foreign, f"foreign: {foreign}")
            case(f"{name} links no dynamic zlib", not any("libz." in library for library in libraries))
        else:
            case(f"{name} is {ELF_MACHINE[config['arch']]} ELF", "ELF" in kind and ELF_MACHINE[config["arch"]] in kind, kind)
            case(f"{name} is statically linked", "static-pie linked" in kind or "statically linked" in kind, kind)
            headers = output(["readelf", "-lW", str(binary)])
            case(f"{name} has no INTERP", "INTERP" not in headers)
            stack = gnu_stack_size(headers)
            case(
                f"{name} thread stack is {MUSL_THREAD_STACK_BYTES} B",
                stack == MUSL_THREAD_STACK_BYTES,
                f"PT_GNU_STACK size {stack}",
            )
            dynamic = output(["readelf", "-dW", str(binary)])
            case(f"{name} has no NEEDED", "(NEEDED)" not in dynamic, dynamic)
            case(f"{name} has no glibc symbol versions", b"GLIBC_" not in data)
            encoders = output([str(binary), "-hide_banner", "-encoders"])
            apple = [word for word in ("videotoolbox", "aac_at", "audiotoolbox") if word in encoders]
            case(f"{name} has no Apple encoders", not apple, f"found: {apple}")


def archive_name(version, tag, target, profile_name):
    return f"ffmpeg-{version}+{tag}-{target}-{profile_name}"


def tar_entry(name, mode, size=0, kind=tarfile.REGTYPE):
    info = tarfile.TarInfo(name)
    info.type = kind
    info.mode = mode
    info.size = size
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    return info


def write_deterministic_archive(path, root_name, files):
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    directories = {root_name}
    for relative in files:
        parent = pathlib.PurePosixPath(relative).parent
        while str(parent) != ".":
            directories.add(f"{root_name}/{parent}")
            parent = parent.parent
    with part.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for directory in sorted(directories):
                    archive.addfile(tar_entry(directory, 0o755, kind=tarfile.DIRTYPE))
                for relative in sorted(files):
                    data, executable = files[relative]
                    info = tar_entry(f"{root_name}/{relative}", 0o755 if executable else 0o644, len(data))
                    archive.addfile(info, io.BytesIO(data))
    part.replace(path)


def package(target, profile_name, tag):
    if not RELEASE_TAG.match(tag):
        fail(f"release tag {tag!r} must be YYYYMMDD, YYYYMMDD-rN, or local")
    lock = load_sources()
    profile, _ = load_profile(profile_name)
    target_config(profile, target)
    stage, _, _ = build_paths(profile_name, target)
    if not stage_complete(stage, profile["artifact"]):
        fail(f"stage {stage} is incomplete; run build first")
    manifest = json.loads((stage / "share" / "ffmpeg-build" / "manifest.json").read_text())
    version = lock["sources"]["ffmpeg"]["version"]
    if manifest.get("profile") != profile_name or manifest.get("target") != target:
        fail(f"stage manifest is for {manifest.get('profile')}/{manifest.get('target')}")
    if manifest.get("sources", {}).get("ffmpeg", {}).get("version") != version:
        fail("stage manifest FFmpeg version disagrees with sources.lock.json")
    name = archive_name(version, tag, target, profile_name)
    manifest["release"] = {"tag": tag, "archive": f"{name}.tar.gz"}
    files = {}
    for path in sorted(stage.rglob("*")):
        if path.is_symlink() or not path.is_file():
            if path.is_symlink():
                fail(f"stage contains a symlink: {path}")
            continue
        relative = path.relative_to(stage).as_posix()
        files[relative] = (path.read_bytes(), os.access(path, os.X_OK))
    files["share/ffmpeg-build/manifest.json"] = (
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
        False,
    )
    destination = DIST / f"{name}.tar.gz"
    write_deterministic_archive(destination, name, files)
    print(f"{sha256_file(destination)}  {destination.name}")
    return destination


def parse_archive_name(filename):
    match = ARCHIVE_NAME.match(filename)
    if not match:
        fail(f"{filename} is not ffmpeg-<upstream>+<tag>-<target>-<profile>.tar.gz")
    return match.groupdict()


def archive_member_problems(members, root_name):
    problems = []
    for member in members:
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            problems.append(f"unsafe path {member.name}")
        elif path.parts[0] != root_name:
            problems.append(f"outside root {member.name}")
        if not (member.isfile() or member.isdir()):
            problems.append(f"not a file or directory: {member.name}")
        if member.uid or member.gid or member.mtime:
            problems.append(f"non-normalized owner or mtime: {member.name}")
    return problems


def qualify(archive_path):
    archive_path = archive_path.resolve()
    parsed = parse_archive_name(archive_path.name)
    lock = load_sources()
    profile_name, target, tag = parsed["profile"], parsed["target"], parsed["tag"]
    profile, _ = load_profile(profile_name)
    config = target_config(profile, target)
    require_native_host(config, target)
    root_name = archive_path.name.removesuffix(".tar.gz")
    check = Audit()
    case = check.case

    work = TMP_ROOT / "qualify" / root_name / "path with spaces"
    if work.parent.exists():
        shutil.rmtree(work.parent)
    work.mkdir(parents=True)
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        problems = archive_member_problems(members, root_name)
        case("archive members are normalized and under the root", not problems, "; ".join(problems[:5]))
        if problems:
            return check.finish()
        archive.extractall(work, filter="data")
    prefix = work / root_name
    case(f"archive root is {root_name}", prefix.is_dir())

    manifest = read_manifest(check, prefix)
    missing = [key for key in MANIFEST_KEYS if key not in manifest]
    case("manifest has the contract keys", not missing, f"missing: {missing}")
    case("manifest profile matches name", manifest.get("profile") == profile_name)
    case("manifest target matches name", manifest.get("target") == target)
    case(
        "manifest FFmpeg version matches name",
        manifest.get("sources", {}).get("ffmpeg", {}).get("version") == parsed["upstream"]
        == lock["sources"]["ffmpeg"]["version"],
    )
    case(
        "manifest sources match the lock",
        all(
            manifest.get("sources", {}).get(name, {}).get("sha256") == lock["sources"][name]["sha256"]
            for name in profile["sources"]
        ),
    )
    case(
        "manifest release matches name",
        manifest.get("release") == {"tag": tag, "archive": archive_path.name},
    )
    missing_notices = [path for path in notice_paths() if not (prefix / path).is_file()]
    case("README and licenses present", not missing_notices, f"missing: {missing_notices}")
    leaked = sorted(
        str(path.relative_to(prefix))
        for path in prefix.rglob("*")
        if path.is_file() and ABSOLUTE_BUILD_TREE.search(path.read_bytes())
    )
    case("no absolute build-tree path in any file", not leaked, f"files: {leaked[:10]}")

    script = ROOT / "tests" / ("qualify-sdk.sh" if profile["artifact"] == "sdk" else "qualify-tools.sh")
    result = subprocess.run(["bash", str(script), str(prefix), target], check=False)
    case(f"{script.name} passes", result.returncode == 0)
    return check.finish()


def main():
    if sys.version_info < (3, 12):
        fail(f"build.py needs Python 3.12 or newer for safe tar extraction; this is {platform.python_version()}")
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch", "build", "audit", "package"):
        command = subparsers.add_parser(name)
        command.add_argument("--target", required=True)
        command.add_argument("--profile", required=True)
        if name == "package":
            command.add_argument("--tag", required=True)
    qualify_command = subparsers.add_parser("qualify")
    qualify_command.add_argument("--archive", required=True, type=pathlib.Path)
    args = parser.parse_args()

    if args.command == "qualify":
        return qualify(args.archive)
    profile, _ = load_profile(args.profile)
    target_config(profile, args.target)
    if args.command == "fetch":
        fetch_profile_sources(profile, load_sources())
        return 0
    if args.command == "build":
        build(args.target, args.profile)
        return 0
    if args.command == "audit":
        return audit(args.target, args.profile)
    if args.command == "package":
        package(args.target, args.profile, args.tag)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
