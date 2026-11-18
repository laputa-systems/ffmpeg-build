import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import bootstrap


class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (bootstrap.ROOT / ".work" / "tmp").mkdir(parents=True, exist_ok=True)

    def test_rejects_malformed_wheel_pin_without_fetching(self):
        with tempfile.TemporaryDirectory(dir=bootstrap.ROOT / '.work' / 'tmp') as directory:
            root = pathlib.Path(directory)
            valid = {"name": bootstrap.PIN, "filename": "wheel.whl", "url": "https://example.invalid/wheel", "sha256": "a" * 64}
            with (
                mock.patch.object(bootstrap, "ROOT", root),
                mock.patch.object(bootstrap, "CACHE", root / "cache"),
                mock.patch("urllib.request.urlopen", side_effect=AssertionError("network access")),
            ):
                for field in ("filename", "url", "sha256"):
                    with self.subTest(field=field):
                        pin = {**valid, field: 123}
                        (root / "sources.lock.json").write_text(json.dumps({"inputs": [pin]}))
                        with self.assertRaisesRegex(TypeError, field):
                            bootstrap._wheel()

    def test_valid_cached_wheel_does_not_fetch(self):
        with tempfile.TemporaryDirectory(dir=bootstrap.ROOT / ".work" / "tmp") as directory:
            root = pathlib.Path(directory)
            cache = root / "cache"
            cache.mkdir()
            wheel = cache / "wheel.whl"
            wheel.write_bytes(b"cached wheel")
            pin = {"name": bootstrap.PIN, "filename": wheel.name, "url": "https://example.invalid/wheel", "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()}
            (root / "sources.lock.json").write_text(json.dumps({"inputs": [pin]}))
            with (
                mock.patch.object(bootstrap, "ROOT", root),
                mock.patch.object(bootstrap, "CACHE", cache),
                mock.patch("urllib.request.urlopen", side_effect=AssertionError("network access")),
            ):
                self.assertEqual(bootstrap._wheel(), wheel)

    def test_lock_shapes_are_validated_before_fetch(self):
        cases = [
            ([], TypeError, "invalid sources lock"),
            ({}, TypeError, "invalid sources lock inputs"),
            ({"inputs": {}}, TypeError, "invalid sources lock inputs"),
            ({"inputs": [None]}, TypeError, "invalid sources lock input"),
            ({"inputs": [{"name": "other"}]}, ValueError, "missing laputa-buildlib source"),
        ]
        with tempfile.TemporaryDirectory(dir=bootstrap.ROOT / ".work" / "tmp") as directory:
            root = pathlib.Path(directory)
            with (
                mock.patch.object(bootstrap, "ROOT", root),
                mock.patch.object(bootstrap, "CACHE", root / "cache"),
                mock.patch("urllib.request.urlopen", side_effect=AssertionError("network access")),
            ):
                for lock, error, message in cases:
                    with self.subTest(lock=lock):
                        (root / "sources.lock.json").write_text(json.dumps(lock))
                        with self.assertRaisesRegex(error, message):
                            bootstrap._wheel()

    def test_download_replaces_only_verified_bytes(self):
        import io

        good = b"local wheel fixture"
        bad = b"corrupt wheel fixture"
        with tempfile.TemporaryDirectory(dir=bootstrap.ROOT / ".work" / "tmp") as directory:
            root = pathlib.Path(directory)
            cache = root / "nested" / "cache"
            wheel = cache / "wheel.whl"
            part = cache / "wheel.whl.part"
            pin = {"name": bootstrap.PIN, "filename": wheel.name, "url": "https://example.invalid/wheel", "sha256": hashlib.sha256(good).hexdigest()}
            (root / "sources.lock.json").write_text(json.dumps({"inputs": [{"name": "other"}, pin]}))
            with (
                mock.patch.object(bootstrap, "ROOT", root),
                mock.patch.object(bootstrap, "CACHE", cache),
                mock.patch("urllib.request.urlopen", side_effect=lambda url, timeout: io.BytesIO(good)) as fetch,
            ):
                self.assertEqual(bootstrap._wheel(), wheel)
                self.assertEqual(wheel.read_bytes(), good)
                self.assertFalse(part.exists())
                fetch.assert_called_once_with(pin["url"], timeout=120)
                fetch.reset_mock()
                self.assertEqual(bootstrap._wheel(), wheel)
                fetch.assert_not_called()
                wheel.write_bytes(b"old cache")
                part.write_bytes(b"stale stage")
                fetch.side_effect = lambda url, timeout: io.BytesIO(bad)
                with self.assertRaisesRegex(SystemExit, "does not match the sha256 pinned for laputa-buildlib"):
                    bootstrap._wheel()
                self.assertEqual(wheel.read_bytes(), b"old cache")
                self.assertFalse(part.exists())
                fetch.side_effect = lambda url, timeout: io.BytesIO(good)
                self.assertEqual(bootstrap._wheel(), wheel)
                self.assertEqual(wheel.read_bytes(), good)
                self.assertFalse(part.exists())

    def test_failed_download_preserves_cache_and_cleans_stage(self):
        with tempfile.TemporaryDirectory(dir=bootstrap.ROOT / ".work" / "tmp") as directory:
            root = pathlib.Path(directory)
            cache = root / "cache"
            cache.mkdir()
            wheel = cache / "wheel.whl"
            part = cache / "wheel.whl.part"
            wheel.write_bytes(b"old cache")
            part.write_bytes(b"stale stage")
            pin = {"name": bootstrap.PIN, "filename": wheel.name, "url": "https://example.invalid/wheel", "sha256": hashlib.sha256(b"new wheel").hexdigest()}
            (root / "sources.lock.json").write_text(json.dumps({"inputs": [pin]}))
            with (
                mock.patch.object(bootstrap, "ROOT", root),
                mock.patch.object(bootstrap, "CACHE", cache),
                mock.patch("urllib.request.urlopen", side_effect=OSError("transport failed")),
                self.assertRaisesRegex(OSError, "transport failed"),
            ):
                bootstrap._wheel()
            self.assertEqual(wheel.read_bytes(), b"old cache")
            self.assertFalse(part.exists())
