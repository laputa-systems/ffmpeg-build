import importlib.util
import pathlib
import unittest
from datetime import UTC, datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("resolve_release", ROOT / ".github" / "scripts" / "resolve_release.py")
resolve_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolve_release)

SHA = "a" * 40


class ResolveReleaseTests(unittest.TestCase):
    def test_defaults_to_utc_date(self):
        now = datetime(2026, 11, 4, 23, 59, tzinfo=UTC)
        self.assertEqual(resolve_release.resolve_release_tag("", SHA, SHA, now), "20261104")

    def test_accepts_revision(self):
        self.assertEqual(resolve_release.resolve_release_tag(" 20261104-r2 ", SHA, SHA), "20261104-r2")

    def test_rejects_other_formats(self):
        for tag in ("v1.0", "2026-11-04", "20261104-2", "latest", "20269999", "20261332-r2"):
            with self.assertRaises(ValueError):
                resolve_release.resolve_release_tag(tag, SHA, SHA)

    def test_rejects_checkout_mismatch(self):
        with self.assertRaises(ValueError):
            resolve_release.resolve_release_tag("20261104", SHA, "b" * 40)

    def test_existing_tag_at_other_commit_rejected(self):
        with self.assertRaises(ValueError):
            resolve_release.verify_existing_tag_target("20261104", SHA, "b" * 40)
        resolve_release.verify_existing_tag_target("20261104", SHA, SHA)
        resolve_release.verify_existing_tag_target("20261104", SHA, None)


if __name__ == "__main__":
    unittest.main()
