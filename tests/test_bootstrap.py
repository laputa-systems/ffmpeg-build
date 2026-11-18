import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import bootstrap


class BootstrapTests(unittest.TestCase):
    def test_rejects_malformed_wheel_pin_without_fetching(self):
        with tempfile.TemporaryDirectory(dir=bootstrap.ROOT / '.work' / 'tmp') as directory:
            root = pathlib.Path(directory)
            valid = {"name": bootstrap.PIN, "filename": "wheel.whl", "url": "https://example.invalid/wheel", "sha256": "a" * 64}
            with mock.patch.object(bootstrap, "ROOT", root), mock.patch.object(bootstrap, "CACHE", root / "cache"):
                with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network access")):
                    for field in ("filename", "url", "sha256"):
                        with self.subTest(field=field):
                            pin = {**valid, field: 123}
                            (root / "sources.lock.json").write_text(json.dumps({"inputs": [pin]}))
                            with self.assertRaisesRegex(ValueError, field):
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
            with mock.patch.object(bootstrap, "ROOT", root), mock.patch.object(bootstrap, "CACHE", cache):
                with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network access")):
                    self.assertEqual(bootstrap._wheel(), wheel)
