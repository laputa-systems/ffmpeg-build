import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import threading
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIM = REPO_ROOT / "bootstrap" / "buildlib-run"
LOCK = REPO_ROOT / "bootstrap" / "python.lock"


class ShimFixture:
    def __init__(self, root: Path):
        self.root = root
        self.cache = root / "cache"
        self.scripts = root / "scripts"
        self.scripts.mkdir(parents=True)
        shutil.copy(SHIM, self.scripts / "buildlib-run")
        self.data = root / "data"
        self.data.mkdir()
        payload = root / "payload" / "python" / "bin"
        payload.mkdir(parents=True)
        python = payload / "python3.15"
        python.write_text('#!/bin/sh\nif [ "$2" != "import sys" ]; then echo executed; fi\n')
        python.chmod(0o755)
        self.archive = self.data / "python.tar.xz"
        with tarfile.open(self.archive, "w:xz") as tar:
            tar.add(payload.parent, arcname="python")
        uv_dir = root / "uv-fixture" / "uv-test"
        uv_dir.mkdir(parents=True)
        uv = uv_dir / "uv"
        uv.write_text('#!/bin/sh\nexit 1\n')
        uv.chmod(0o755)
        self.uv_archive = self.data / "uv.tar.gz"
        with tarfile.open(self.uv_archive, "w:gz") as tar:
            tar.add(uv_dir, arcname="uv-test")
        self.wheel = self.data / "wheel.whl"
        self.wheel.write_bytes(b"wheel fixture")
        handler = partial(SimpleHTTPRequestHandler, directory=str(self.data))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.bin = root / "bin"
        self.bin.mkdir()
        (self.bin / "uname").write_text('#!/bin/sh\ncase "$1" in -s) echo Darwin;; -m) echo arm64;; esac\n')
        (self.bin / "uname").chmod(0o755)
        self.real_curl = shutil.which("curl")
        wrapper = self.bin / "curl"
        wrapper.write_text(
            '#!/bin/sh\nout=\nwhile [ "$#" -gt 0 ]; do\n'
            'case "$1" in -o) out=$2; shift 2;; https://fixture/*) name=${1#https://fixture/}; shift;; '
            '--proto|--proto-redir|--retry) shift 2;; *) shift;; esac\ndone\n'
            f'exec "{self.real_curl}" -fsS -o "$out" "http://127.0.0.1:{self.server.server_port}/$name"\n'
        )
        wrapper.chmod(0o755)
        self.lock = self.scripts / "python.lock"
        self.python_size = self.archive.stat().st_size
        self.python_sha = self.digest(self.archive)
        self.wheel_sha = self.digest(self.wheel)
        self.write_lock()

    @staticmethod
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write_lock(self, *, python_size=None, python_sha=None, wheel_sha=None):
        size = self.python_size if python_size is None else python_size
        sha = self.python_sha if python_sha is None else python_sha
        wheel = self.wheel_sha if wheel_sha is None else wheel_sha
        self.lock.write_text(
            f"release fixture\nuv_version 0.13.7\nuv_python 3.15.2\n"
            f"wheel https://fixture/wheel.whl {wheel}\n"
            f"python aarch64-apple-darwin https://fixture/python.tar.xz {size} {sha}\n"
            f"uv aarch64-apple-darwin https://fixture/uv.tar.gz "
            f"{self.uv_archive.stat().st_size} {self.digest(self.uv_archive)}\n"
        )

    def run(self):
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", BUILDLIB_CACHE=str(self.cache))
        return subprocess.run(
            ["sh", str(self.scripts / "buildlib-run"), "--", "-c", "pass"],
            check=False, env=env, capture_output=True, text=True,
        )

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class VendoredShimTest(unittest.TestCase):
    def setUp(self):
        if os.name == "nt":
            self.skipTest("the buildlib bootstrap is a POSIX sh script")
        root = REPO_ROOT / ".work" / "tmp"
        root.mkdir(parents=True, exist_ok=True)
        self.scratch = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.scratch.cleanup)
        self.fixture = ShimFixture(Path(self.scratch.name))
        self.addCleanup(self.fixture.close)

    def test_verified_archives_and_wheel_run_the_python_from_the_cache(self):
        result = self.fixture.run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("executed", result.stdout)
        self.assertIn("buildlib-run: using python-build", result.stderr)

    def test_injected_wrong_wheel_digest_fails_before_running_python(self):
        self.fixture.write_lock(wheel_sha="0" * 64)
        result = self.fixture.run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sha256 mismatch", result.stderr)
        self.assertNotIn("executed", result.stdout)

    def test_injected_wrong_archive_size_fails_before_extracting(self):
        self.fixture.write_lock(python_size=self.fixture.python_size + 1)
        result = self.fixture.run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"archive size mismatch: {self.fixture.python_size}", result.stderr)
        self.assertNotIn("executed", result.stdout)

    def test_truncated_download_fails_clearly(self):
        truncated = self.fixture.data / "python.tar.xz"
        original = truncated.read_bytes()
        try:
            truncated.write_bytes(original[: len(original) // 2])
            result = self.fixture.run()
        finally:
            truncated.write_bytes(original)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("archive size mismatch", result.stderr)
        self.assertNotIn("executed", result.stdout)


class VendoredBootstrapPinTest(unittest.TestCase):
    def test_vendored_bootstrap_pins_the_same_wheel_as_the_source_lock(self):
        records = {}
        for line in LOCK.read_text().splitlines():
            fields = line.split()
            records.setdefault(fields[0], []).append(fields[1:])
        (wheel_url, wheel_sha), = records["wheel"]
        lock = json.loads((REPO_ROOT / "sources.lock.json").read_text())
        pins = [item for item in lock["inputs"] if item["name"] == "laputa-buildlib"]
        self.assertEqual(len(pins), 1)
        self.assertEqual(pins[0]["url"], wheel_url)
        self.assertEqual(pins[0]["sha256"], wheel_sha)


if __name__ == "__main__":
    unittest.main()
