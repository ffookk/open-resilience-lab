import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import bundle_export as bundles
import private_storage as storage
import resilience_plan as app

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "fictional-household.json"


@unittest.skipUnless(os.name == "posix", "POSIX private bundle workflow")
class BundleTests(unittest.TestCase):
    def setUp(self):
        self.previous = Path.cwd()
        self.directory = tempfile.TemporaryDirectory()
        os.chdir(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(os.chdir, self.previous)
        self.input = Path("PRIVATE_INPUT_NAME.json")
        self.input.write_bytes(EXAMPLE.read_bytes())
        self.original = self.input.read_bytes()
        self.output = Path("private-output/example-bundle")

    def export(self, **options):
        return app.export_bundle(self.input, self.output, presentation=options)

    def test_bundle_contains_private_fixed_files_and_valid_hashes(self):
        with patch("socket.socket", side_effect=AssertionError("Network is forbidden")):
            manifest = self.export()
            self.assertTrue(bundles.verify_bundle(self.output))
        self.assertEqual({p.name for p in self.output.iterdir()}, bundles.BUNDLE_NAMES)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.output.parent.stat().st_mode), 0o700)
        for item in self.output.iterdir():
            self.assertEqual(stat.S_IMODE(item.stat().st_mode), 0o600)
        for name in bundles.PAYLOAD_NAMES:
            payload = (self.output / name).read_bytes()
            self.assertEqual(manifest["files"][name], {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
        serialized = (self.output / "manifest.json").read_text()
        for value in (str(self.input), self.directory.name, "Fictional household example"):
            self.assertNotIn(value, serialized)
        self.assertEqual(self.input.read_bytes(), self.original)

    def test_plaintext_preserves_multiline_data_and_cards_escape_html(self):
        plan = json.loads(self.original)
        plan["contacts"][0]["name"] = '<script>PRIVATE_MARKER</script>'
        plan["contacts"][0]["contact"] = 'First line\nSecond line & "quoted"'
        plan["meeting_points"][0]["instructions"] = '<img src="https://example.invalid/a">\nOther arrangement'
        plan["notes"] = "PRIVATE_NOTES_ONLY"
        self.input.write_text(json.dumps(plan))
        self.export(large_text=True, paper="letter", landscape=True)
        text = (self.output / "plan.txt").read_text()
        self.assertIn(plan["contacts"][0]["contact"], text)
        self.assertIn("PRIVATE_NOTES_ONLY", text)
        for filename in ("plan.html", "cards.html"):
            html = (self.output / filename).read_text()
            self.assertNotIn("<script>", html)
            self.assertNotIn("<img", html)
            self.assertIn("&lt;script&gt;PRIVATE_MARKER&lt;/script&gt;", html)
        cards = (self.output / "cards.html").read_text()
        self.assertEqual(cards.count("<article>"), 2)
        self.assertIn("First line\nSecond line &amp; &quot;quoted&quot;", cards)
        self.assertNotIn("PRIVATE_NOTES_ONLY", cards)
        self.assertIn("size:letter landscape", cards)

    def test_bundle_html_has_no_active_external_resources(self):
        self.export()
        for filename in ("plan.html", "cards.html"):
            document = (self.output / filename).read_text()
            self.assertNotRegex(document, r"(?i)<\s*(script|link|img|iframe|object|embed|form|base|video|audio)\b")
            self.assertNotRegex(document, r"(?i)\b(src|action)\s*=|@import|url\s*\(")
            self.assertNotRegex(document, r'(?i)\bhref\s*=\s*(?!"#[a-z][a-z-]*")')
            self.assertIn("default-src 'none'", document)

    def test_tampered_missing_and_unexpected_entries_fail_safely(self):
        self.export()
        target = self.output / "plan.txt"
        original = target.read_bytes()
        target.write_text("PRIVATE_TAMPER_MARKER")
        with self.assertRaises(storage.StorageError) as failed:
            bundles.verify_bundle(self.output)
        self.assertNotIn("PRIVATE_TAMPER_MARKER", str(failed.exception))
        target.unlink()
        with self.assertRaises(storage.StorageError):
            bundles.verify_bundle(self.output)
        target.write_bytes(original)
        (self.output / "PRIVATE_EXTRA_NAME").write_text("Unexpected")
        with self.assertRaises(storage.StorageError) as failed:
            bundles.verify_bundle(self.output)
        self.assertNotIn("PRIVATE_EXTRA_NAME", str(failed.exception))

    def test_manifest_last_marks_completion_and_failure_removes_payloads(self):
        order = []
        writer, publisher = bundles.write_private_bytes, bundles.publish_private_bytes
        def record_write(parent, name, payload, **kwargs):
            order.append(name)
            self.assertFalse((self.output / "manifest.json").exists())
            return writer(parent, name, payload, **kwargs)
        def record_publish(parent, name, payload, **kwargs):
            self.assertEqual(set(os.listdir(parent)), set(bundles.PAYLOAD_NAMES))
            order.append(name)
            return publisher(parent, name, payload, **kwargs)
        with patch.object(bundles, "write_private_bytes", side_effect=record_write), patch.object(bundles, "publish_private_bytes", side_effect=record_publish):
            self.export()
        self.assertEqual(order, [*bundles.PAYLOAD_NAMES, "manifest.json"])
        self.assertTrue(bundles.verify_bundle(self.output))

    def test_write_error_or_cancellation_removes_this_operations_files(self):
        original = bundles.write_private_bytes
        for failure in (OSError("PRIVATE_ERROR"), KeyboardInterrupt()):
            def interrupt(parent, name, payload, **kwargs):
                if name == "plan.txt":
                    raise failure
                return original(parent, name, payload, **kwargs)
            expected = app.PlanError if isinstance(failure, OSError) else KeyboardInterrupt
            with patch.object(bundles, "write_private_bytes", side_effect=interrupt), self.assertRaises(expected) as failed:
                self.export()
            self.assertNotIn("PRIVATE_ERROR", str(failed.exception))
            self.assertFalse(self.output.exists())
            self.assertEqual(self.input.read_bytes(), self.original)

    def test_manifest_write_failure_removes_payloads(self):
        with patch.object(bundles, "publish_private_bytes", side_effect=OSError("PRIVATE_ERROR")), self.assertRaises(app.PlanError):
            self.export()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.output.parent.iterdir()), [])

    def test_cleanup_preserves_an_unrelated_concurrent_file(self):
        original = bundles.write_private_bytes
        def interrupt(parent, name, payload, **kwargs):
            if name == "plan.txt":
                storage.write_private_bytes(parent, "unrelated.txt", b"KEEP")
                raise OSError("Simulated failure")
            return original(parent, name, payload, **kwargs)
        with patch.object(bundles, "write_private_bytes", side_effect=interrupt), self.assertRaises(app.PlanError):
            self.export()
        self.assertEqual({p.name for p in self.output.iterdir()}, {"unrelated.txt"})
        self.assertEqual((self.output / "unrelated.txt").read_bytes(), b"KEEP")
        with self.assertRaises(storage.StorageError):
            bundles.verify_bundle(self.output)

    def test_existing_destination_is_never_overwritten(self):
        self.export()
        snapshot = {p.name: p.read_bytes() for p in self.output.iterdir()}
        with self.assertRaises(app.PlanError):
            self.export()
        self.assertEqual({p.name: p.read_bytes() for p in self.output.iterdir()}, snapshot)

    def test_empty_destination_and_parent_links_are_rejected(self):
        self.output.parent.mkdir(mode=0o700)
        self.output.mkdir(mode=0o700)
        with self.assertRaises(app.PlanError):
            self.export()
        self.assertEqual(list(self.output.iterdir()), [])
        self.output.rmdir()
        self.output.parent.rmdir()
        Path("other").mkdir(mode=0o700)
        self.output.parent.symlink_to(Path("other").resolve(), target_is_directory=True)
        with self.assertRaises(app.PlanError):
            self.export()
        self.assertEqual(list(Path("other").iterdir()), [])

    def test_nonregular_or_linked_payloads_and_directories_are_rejected(self):
        self.export()
        target = self.output / "plan.txt"
        payload = target.read_bytes()
        target.unlink()
        for kind in ("directory", "symlink", "hardlink", "fifo"):
            external = Path("external.txt")
            external.write_bytes(payload)
            if kind == "directory": target.mkdir()
            elif kind == "symlink": target.symlink_to(external.resolve())
            elif kind == "hardlink": os.link(external, target)
            else: os.mkfifo(target)
            with self.subTest(kind=kind), self.assertRaises(storage.StorageError):
                bundles.verify_bundle(self.output)
            target.rmdir() if kind == "directory" else target.unlink()
            external.unlink()
        target.write_bytes(payload)
        Path("linked-bundle").symlink_to(self.output.resolve(), target_is_directory=True)
        with self.assertRaises(storage.StorageError):
            bundles.verify_bundle("linked-bundle")

    def test_manifest_paths_versions_duplicates_and_oversize_are_rejected(self):
        self.export()
        manifest_path = self.output / "manifest.json"
        original = json.loads(manifest_path.read_text())
        wrong_paths = copy.deepcopy(original)
        wrong_paths["files"]["../PRIVATE_VALUE"] = wrong_paths["files"].pop("plan.txt")
        bad_version = dict(original, bundle_format=True)
        invalids = [json.dumps(wrong_paths), json.dumps(bad_version), '{"PRIVATE_VALUE":',
                    '{"bundle_format":1,"bundle_format":1}', ' ' * (bundles.MAX_MANIFEST_BYTES + 1)]
        for value in invalids:
            manifest_path.write_text(value)
            with patch.object(bundles, "read_regular_bytes", wraps=storage.read_regular_bytes) as reads:
                with self.assertRaises(storage.StorageError) as failed:
                    bundles.verify_bundle(self.output)
                self.assertEqual([call.args[1] for call in reads.call_args_list], ["manifest.json"])
                self.assertNotIn("PRIVATE_VALUE", str(failed.exception))

    def test_payload_size_cap_and_invalid_input_prevent_unbounded_reads_or_exports(self):
        self.export()
        with (self.output / "plan.txt").open("wb") as stream:
            stream.truncate(bundles.MAX_BUNDLE_FILE_BYTES + 1)
        with self.assertRaises(storage.StorageError):
            bundles.verify_bundle(self.output)
        self.input.write_text('{"PRIVATE_VALUE":')
        with self.assertRaises(app.PlanError) as failed:
            app.export_bundle(self.input, "private-output/never-created")
        self.assertNotIn("PRIVATE_VALUE", str(failed.exception))
        self.assertFalse(Path("private-output/never-created").exists())

    def test_cli_outputs_only_fixed_status_and_fixed_errors(self):
        with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(app.main(["bundle", str(self.input), "--output", str(self.output), "--paper", "a4"]), 0)
            self.assertEqual(app.main(["verify-bundle", str(self.output)]), 0)
            self.assertEqual(app.main(["bundle", str(self.input), "--output", str(self.output)]), 2)
            self.assertEqual(app.main(["bundle", str(self.input), "--output", "private-output/PRIVATE_PATH", "--paper", "PRIVATE_OPTION"]), 2)
        combined = output.getvalue() + error.getvalue()
        for value in ("PRIVATE_INPUT_NAME", "PRIVATE_PATH", "PRIVATE_OPTION", str(self.output), self.directory.name):
            self.assertNotIn(value, combined)
        with patch.object(app, "export_bundle", side_effect=KeyboardInterrupt()), contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(app.main(["bundle", str(self.input), "--output", "private-output/PRIVATE_PATH"]), 130)
        self.assertNotIn("PRIVATE_PATH", error.getvalue())


if __name__ == "__main__":
    unittest.main()
