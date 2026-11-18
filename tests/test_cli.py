import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ControllerCommandTests(unittest.TestCase):
    def run_command(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "build.py"), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )

    def test_version_prints_the_locked_release(self):
        lock = json.loads((ROOT / "sources.lock.json").read_text())
        expected = next(entry["version"] for entry in lock["inputs"] if entry["name"] == "ffmpeg")
        result = self.run_command("version")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, f"{expected}\n", ""))

    def test_audit_rejects_a_target_outside_the_profile(self):
        result = self.run_command("audit", "--target", "not-a-target", "--profile", "tools")
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertEqual(result.stderr, "error: target not-a-target is not in profile tools\n")

    def test_package_requires_a_profile(self):
        result = self.run_command("package", "--target", "aarch64-apple-darwin")
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertEqual(
            result.stderr.splitlines()[-1],
            "build.py package: error: the following arguments are required: --profile",
        )
