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
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
WORK = ROOT / ".work"
CACHE = WORK / "cache" / "sources"
BUILD_ROOT = WORK / "build"
STAGE_ROOT = WORK / "stage"
TMP_ROOT = WORK / "tmp"

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


def load_profile(name):
    path = ROOT / "profiles" / f"{name}.json"
    profile = read_json(path)
    if profile.get("profile") != name:
        fail(f"{path} does not declare profile {name}")
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


def platform_toolchain(config):
    info = {
        "host": platform.platform(),
        "cpu_baseline": config.get("cpu_baseline", ""),
        "deployment_target": config.get("deployment_target", ""),
    }
    cc = config.get("cc", "cc")
    if config["platform"] == "macos":
        info["cc"] = output([cc, "--version"]).splitlines()[0]
        info["sdk"] = output(["xcrun", "--sdk", "macosx", "--show-sdk-path"])
        info["sdk_version"] = output(["xcrun", "--sdk", "macosx", "--show-sdk-version"])
        info["sysroot"] = info["sdk"]
    else:
        info["cc"] = output([cc, "--version"]).splitlines()[0]
        info["sdk"] = config.get("sdk", "")
        info["sdk_version"] = config.get("sdk_version", "")
        info["sysroot"] = config.get("sysroot", "")
    return info


def configure_args_for(profile, target, stage, toolchain):
    config = target_config(profile, target)
    requested = requested_components(profile, target)
    cc = config.get("cc", "cc")
    args = [
        f"--prefix={stage}",
        "--disable-shared",
        "--enable-static",
        "--disable-programs",
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
    if toolchain["sysroot"]:
        args.append(f"--sysroot={toolchain['sysroot']}")
    extra_cflags = ["-O2", "-fPIC"]
    extra_ldflags = []
    if config["platform"] == "macos":
        target_version = config.get("deployment_target")
        if not target_version:
            fail(f"macOS target {target} lacks deployment_target")
        extra_cflags.append(f"-mmacosx-version-min={target_version}")
        extra_ldflags.append(f"-mmacosx-version-min={target_version}")
    extra_cflags.append(f"-I{stage}/include")
    extra_ldflags.append(f"-L{stage}/lib")
    args.append("--extra-cflags=" + " ".join(extra_cflags))
    args.append("--extra-ldflags=" + " ".join(extra_ldflags))
    args.extend(config.get("configure_flags", []))
    for category, names in requested.items():
        option = CONFIGURE_OPTION[category]
        for name in names:
            args.append(f"{option}={configure_component(category, name)}")
    return args


def dep_env(config, stage, toolchain):
    env = os.environ.copy()
    env["TMPDIR"] = str(TMP_ROOT)
    env["CC"] = config.get("cc", "cc")
    env["PKG_CONFIG_PATH"] = str(stage / "lib" / "pkgconfig")
    env["PKG_CONFIG_LIBDIR"] = str(stage / "lib" / "pkgconfig")
    cflags = ["-O2", "-fPIC"]
    ldflags = []
    if config["platform"] == "macos":
        cflags.extend(["-isysroot", toolchain["sdk"]])
        cflags.append(f"-mmacosx-version-min={config['deployment_target']}")
        ldflags.extend(["-isysroot", toolchain["sdk"]])
        ldflags.append(f"-mmacosx-version-min={config['deployment_target']}")
        env["MACOSX_DEPLOYMENT_TARGET"] = config["deployment_target"]
    env["CFLAGS"] = " ".join(cflags)
    env["CXXFLAGS"] = env["CFLAGS"]
    env["LDFLAGS"] = " ".join(ldflags)
    return env


def ffmpeg_env(stage):
    env = os.environ.copy()
    env["TMPDIR"] = str(TMP_ROOT)
    env["PKG_CONFIG_PATH"] = str(stage / "lib" / "pkgconfig")
    env["PKG_CONFIG_LIBDIR"] = str(stage / "lib" / "pkgconfig")
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


def build_zlib(source_dir, stage, env):
    run(["./configure", f"--prefix={stage}", "--static"], cwd=source_dir, env=env)
    run(["make", f"-j{jobs()}"], cwd=source_dir, env=env)
    run(["make", "install"], cwd=source_dir, env=env)


def build_dav1d(source_dir, build_dir, stage, env):
    if build_dir.exists():
        shutil.rmtree(build_dir)
    run(
        [
            "meson",
            "setup",
            str(build_dir),
            str(source_dir),
            f"--prefix={stage}",
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
        text = text.replace(str(stage), stage_prefix)
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


def prune_stage(stage):
    for relative in ("share/man", "share/ffmpeg", "share/doc", "share/examples"):
        path = stage / relative
        if path.exists():
            shutil.rmtree(path)
    for relative in ("bin/ffmpeg", "bin/ffprobe", "bin/ffplay"):
        path = stage / relative
        if path.exists():
            path.unlink()


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


def stage_complete(stage):
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
        "toolchain": toolchain,
    }


def write_manifest(stage, manifest):
    path = stage / "share" / "ffmpeg-build" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path}")


def build(target, profile_name):
    lock = load_sources()
    profile, profile_path = load_profile(profile_name)
    config = target_config(profile, target)
    stage = STAGE_ROOT / target / profile_name
    build_dir = BUILD_ROOT / target / profile_name
    toolchain = platform_toolchain(config)
    args = configure_args_for(profile, target, stage, toolchain)
    fingerprint = build_fingerprint(profile_path, target, profile_name, args, toolchain)
    stamp_path = build_dir / "stamp.json"
    if stamp_path.is_file() and stage_complete(stage):
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

    env = dep_env(config, stage, toolchain)
    print(f"build zlib {lock['sources']['zlib']['version']}")
    build_zlib(zlib_source, stage, env)
    print(f"build dav1d {lock['sources']['dav1d']['version']}")
    build_dav1d(dav1d_source, build_dir / "dav1d", stage, env)

    ffmpeg_build = build_dir / "ffmpeg"
    ffmpeg_build.mkdir()
    print(f"configure FFmpeg {lock['sources']['ffmpeg']['version']}")
    run([str(ffmpeg_source / "configure"), *args], cwd=ffmpeg_build, env=ffmpeg_env(stage))
    print(f"build FFmpeg {lock['sources']['ffmpeg']['version']}")
    run(["make", f"-j{jobs()}"], cwd=ffmpeg_build, env=ffmpeg_env(stage))
    run(["make", "install"], cwd=ffmpeg_build, env=ffmpeg_env(stage))

    prune_stage(stage)
    normalize_pc(stage)
    manifest = manifest_for(profile, target, ffmpeg_build, stage, args, toolchain)
    write_manifest(stage, manifest)
    if not stage_complete(stage):
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


def audit(target, profile_name):
    lock = load_sources()
    profile, _ = load_profile(profile_name)
    config = target_config(profile, target)
    stage = STAGE_ROOT / target / profile_name
    build_dir = BUILD_ROOT / target / profile_name
    results = []

    def case(name, ok, detail=""):
        status = "PASS" if ok else "FAIL"
        line = f"{status} audit: {name}"
        if detail and not ok:
            line += f": {detail}"
        print(line)
        results.append(ok)

    if not build_dir.is_dir():
        fail(f"missing build tree {build_dir}; run build first")
    if not stage.is_dir():
        fail(f"missing stage {stage}; run build first")

    version = lock["sources"]["ffmpeg"]["version"]
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

    resolved = parse_components(build_dir / "ffmpeg")
    config_mak = parse_config_mak(build_dir / "ffmpeg")
    requested = requested_components(profile, target)
    args = configure_args_for(profile, target, stage, platform_toolchain(config))
    configuration = parse_configuration(config_mak)
    external_libraries = parse_external_libraries(config_mak)

    for category in ("encoders", "muxers", "devices"):
        names = resolved.get(category, [])
        case(f"no {category}", not names, f"{category}: {names}")

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

    selected = auto_selected(requested, resolved)
    print(f"auto-selected: {json.dumps(selected, sort_keys=True)}")

    manifest_path = stage / "share" / "ffmpeg-build" / "manifest.json"
    manifest = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text())
            case("manifest readable", True)
        except json.JSONDecodeError as exc:
            case("manifest readable", False, str(exc))
    else:
        case("manifest readable", False, f"missing {manifest_path}")

    if manifest:
        case("manifest contract", manifest.get("contract") == 1)
        case("manifest producer", bool(manifest.get("producer", {}).get("commit")))
        case("manifest profile and target", manifest.get("profile") == profile_name and manifest.get("target") == target)
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
        toolchain = manifest.get("toolchain", {})
        case(
            "manifest toolchain",
            bool(toolchain.get("cc"))
            and bool(toolchain.get("sysroot"))
            and bool(toolchain.get("cpu_baseline")),
            f"toolchain: {toolchain}",
        )
        case("manifest configure arguments", manifest.get("configure_args") == args)
        case("manifest effective configure", manifest.get("configure") == configuration)

    case(
        "external libraries allowed",
        set(external_libraries) <= set(config.get("external_libraries", [])),
        f"extra: {sorted(set(external_libraries) - set(config.get('external_libraries', [])))}",
    )
    case(
        "external libraries recorded",
        external_libraries == manifest.get("external_libraries", []),
    )
    case("zlib enabled", "CONFIG_ZLIB=yes" in config_mak)
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

    case(
        "PIC enabled",
        "--enable-pic" in args and re.search(r"-fPIC\b|-fpic\b", config_mak) is not None,
    )
    case("no LTO flags", "-flto" not in config_mak)

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
                if "bitcode" in line.lower():
                    archive_problems.append(f"{archive.name}: LTO bitcode")
                    break
                if config["platform"] == "macos" and "Mach-O" not in line:
                    archive_problems.append(f"{archive.name}: {line}")
                    break
                if config["platform"] == "linux" and "ELF" not in line:
                    archive_problems.append(f"{archive.name}: {line}")
                    break
        finally:
            if work.exists():
                shutil.rmtree(work)
    case(
        "archives contain object code, not bitcode",
        not archive_problems,
        "; ".join(archive_problems[:5]),
    )

    passed = sum(1 for result in results if result)
    failed = len(results) - passed
    print(f"TOTAL {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch", "build", "audit"):
        command = subparsers.add_parser(name)
        command.add_argument("--target", required=True)
        command.add_argument("--profile", required=True)
    args = parser.parse_args()

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
    return 2


if __name__ == "__main__":
    sys.exit(main())
