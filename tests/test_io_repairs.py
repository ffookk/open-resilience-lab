"""Regression checks for bounded plan reads and ownership-aware output cleanup."""
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import private_storage as storage
import resilience_plan as app

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "POSIX file types and private permissions")
class InputAndOutputRepairTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_fifo_input_returns_a_fixed_error_without_waiting_for_a_writer(self):
        path = self.root / "fictional-pipe.json"
        os.mkfifo(path)
        result = subprocess.run([sys.executable, str(ROOT / "resilience_plan.py"), str(path), "--check"],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Error:", result.stderr)
        self.assertNotIn(str(path), result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_nonregular_input_is_refused_and_regular_input_still_loads(self):
        for path in (self.root, Path(os.devnull)):
            with self.subTest(kind=path.name), self.assertRaises(app.PlanError):
                app.load_plan(path)
        plan = app.load_plan(ROOT / "examples" / "fictional-household.json")
        self.assertEqual(plan["schema_version"], 1)

    def test_every_new_html_ancestor_uses_private_permissions(self):
        source = self.root / "input.json"
        source.write_text("source")
        output = self.root / "new-root" / "nested" / "deeper" / "plan.html"
        previous = os.umask(0o022)
        try:
            app.save_plan("Example document", output, source)
        finally:
            os.umask(previous)
        for parent in (output.parent, output.parent.parent, output.parent.parent.parent):
            self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        self.assertEqual(source.read_text(), "source")

    def test_failed_private_write_preserves_a_concurrent_replacement(self):
        parent = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, parent)
        def fail_after_replacement(descriptor):
            (self.root / "payload.txt").rename(self.root / "original.txt")
            (self.root / "payload.txt").write_bytes(b"Concurrent content")
            raise OSError("Synthetic write failure")
        with patch.object(storage.os, "fsync", side_effect=fail_after_replacement):
            with self.assertRaisesRegex(OSError, "Synthetic write failure"):
                storage.write_private_bytes(parent, "payload.txt", b"Original content")
        self.assertEqual((self.root / "payload.txt").read_bytes(), b"Concurrent content")
        self.assertEqual((self.root / "original.txt").read_bytes(), b"Original content")

    def test_cleanup_keeps_cancellation_when_the_partial_file_is_already_gone(self):
        parent = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, parent)
        def cancel_after_removal(descriptor):
            (self.root / "payload.txt").unlink()
            raise KeyboardInterrupt
        with patch.object(storage.os, "fsync", side_effect=cancel_after_removal):
            with self.assertRaises(KeyboardInterrupt):
                storage.write_private_bytes(parent, "payload.txt", b"Example content")
        self.assertFalse((self.root / "payload.txt").exists())

    def test_failed_publication_preserves_a_replaced_temporary_entry(self):
        parent = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, parent)
        replacement = None
        def fail_after_replacement(source, destination, **kwargs):
            nonlocal replacement
            replacement = self.root / source
            replacement.rename(self.root / "original.txt")
            replacement.write_bytes(b"Concurrent content")
            raise OSError("Synthetic publication failure")
        with patch.object(storage.os, "link", side_effect=fail_after_replacement):
            with self.assertRaisesRegex(OSError, "Synthetic publication failure"):
                storage.publish_private_bytes(parent, "payload.txt", b"Original content")
        self.assertEqual(replacement.read_bytes(), b"Concurrent content")
        self.assertFalse((self.root / "payload.txt").exists())

    def test_legacy_output_cleanup_preserves_concurrent_replacements(self):
        source = self.root / "input.json"
        source.write_text("source")
        fdopen = os.fdopen
        for force in (False, True):
            output = self.root / ("forced.html" if force else "exclusive.html")
            replacement = []
            class FailedWriter:
                def __init__(self, descriptor, *args, **kwargs):
                    self.stream = fdopen(descriptor, *args, **kwargs)
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    self.stream.close()
                def write(self, text):
                    target = next(self_root.glob(".plan-*")) if force else output
                    target.rename(self_root / ("owned-force" if force else "owned-exclusive"))
                    target.write_text("Concurrent content")
                    replacement.append(target)
                    raise OSError("Synthetic write failure")
            self_root = self.root
            with patch.object(app.os, "fdopen", side_effect=FailedWriter), self.assertRaises(app.PlanError):
                app.save_plan("Original content", output, source, force=force)
            self.assertEqual(replacement[0].read_text(), "Concurrent content")
            replacement[0].unlink()
