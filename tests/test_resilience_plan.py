import contextlib
import copy
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

import resilience_plan as app

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "fictional-household.json"


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_example_validates_and_generates_bilingual_content(self):
        document = app.render_plan(app.load_plan(EXAMPLE))
        self.assertIn("紧急联系人 / Contacts", document)
        self.assertIn(self.plan["contacts"][0]["name"], document)
        self.assertIn("@media print", document)

    def test_every_user_string_is_escaped(self):
        attack = '<script>alert("PRIVATE")</script><img src="https://example.invalid/a">'
        self.plan["title"] = attack
        self.plan["region"] = attack
        self.plan["contacts"][0] = dict.fromkeys(("name", "role", "contact"), attack)
        self.plan["meeting_points"][0] = dict.fromkeys(("label", "instructions"), attack)
        self.plan["household"][0] = dict.fromkeys(("name", "needs"), attack)
        self.plan["notes"] = attack
        self.plan["sources"] = [{"title": attack, "url": "https://example.invalid/path", "verified_on": "2026-09-20"}]
        document = app.render_plan(self.plan)
        self.assertNotIn("<script", document.lower())
        self.assertNotIn("<img", document.lower())
        self.assertIn("&lt;script&gt;", document)
        self.assertIn("&quot;PRIVATE&quot;", document)

    def test_output_has_no_active_external_resources(self):
        document = app.render_plan(self.plan)
        self.assertNotRegex(document, r"(?i)<\s*(script|link|img|iframe|object|embed|form|base|video|audio)\b")
        self.assertNotRegex(document, r"(?i)\b(src|href|action)\s*=|@import|url\s*\(")
        self.assertIn("default-src 'none'", document)
        self.assertIn("connect-src 'none'", document)

    def test_missing_unknown_wrong_type_and_oversized_fields_rejected(self):
        changes = [lambda p: p.pop("contacts"), lambda p: p.update(secret="PRIVATE"),
                   lambda p: p.update(title=1), lambda p: p.update(schema_version=True),
                   lambda p: p.update(title=" " * 4), lambda p: p.update(title="x" * 121),
                   lambda p: p.update(contacts=[]), lambda p: p.update(contacts={}),
                   lambda p: p.update(contacts=p["contacts"] * 21),
                   lambda p: p.update(meeting_points=p["meeting_points"] * 11),
                   lambda p: p.update(reviewed_on="2026-02-30"),
                   lambda p: p["meeting_points"][0].update(instructions="x" * 2001),
                   lambda p: p["household"][0].update(needs="x" * 1001),
                   lambda p: p.update(notes="x\x1b[31m"), lambda p: p.update(notes="\ud800")]
        for change in changes:
            with self.subTest(change=change):
                plan = copy.deepcopy(self.plan)
                change(plan)
                with self.assertRaises(app.PlanError):
                    app.validate_plan(plan)

    def test_sensitive_or_active_source_urls_rejected(self):
        for address in ("javascript:alert(1)", "http://example.invalid/", "https://" + "u:p" + "@example.invalid/",
                        "https://" + "@example.invalid/", "https://" + ":" + "@example.invalid/",
                        "https://example.invalid/?secret=x", "https://example.invalid/#private",
                        "https://example.invalid/a b", "https://[", "https://example.invalid\\path"):
            with self.subTest(address=address):
                self.plan["sources"] = [{"title": "Example", "url": address, "verified_on": "2026-09-20"}]
                with self.assertRaises(app.PlanError):
                    app.validate_plan(self.plan)

    def test_invalid_json_duplicate_keys_size_and_errors_do_not_echo_data(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "secret-private-name.json"
            for payload in (b'{"PRIVATE SECRET":', b'{"PRIVATE": 1, "PRIVATE": 2}',
                            b"\xffPRIVATE", b" " * (app.MAX_INPUT_BYTES + 1),
                            ("9" * 10000).encode(),
                            ("[" * 2000 + "PRIVATE").encode()):
                path.write_bytes(payload)
                with contextlib.redirect_stderr(io.StringIO()) as errors:
                    self.assertEqual(app.main([str(path)]), 2)
                self.assertNotIn("PRIVATE", errors.getvalue())
                self.assertNotIn(str(path), errors.getvalue())

    def test_existing_output_needs_force_and_input_is_always_protected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.json"
            source.write_text("source", encoding="utf-8")
            output = Path(folder) / "private-output" / "plan.html"
            app.save_plan("first", output, source)
            with self.assertRaises(app.PlanError):
                app.save_plan("second", output, source)
            self.assertEqual(output.read_text(), "first")
            app.save_plan("second", output, source, force=True)
            self.assertEqual(output.read_text(), "second")
            with self.assertRaises(app.PlanError):
                app.save_plan("destroyed", source, source, force=True)
            self.assertEqual(source.read_text(), "source")
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(output.parent.stat().st_mode), 0o700)

    @unittest.skipUnless(os.name == "posix", "POSIX link behavior")
    def test_links_cannot_overwrite_input_or_unrelated_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.json"
            source.write_text("original")
            hardlink = Path(folder) / "hardlink.html"
            os.link(source, hardlink)
            symlink = Path(folder) / "symlink.html"
            symlink.symlink_to(source)
            for output in (hardlink, symlink):
                with self.assertRaises(app.PlanError):
                    app.save_plan("destroyed", output, source, force=True)
            unrelated = Path(folder) / "other.txt"
            unrelated.write_text("unrelated")
            symlink.unlink()
            symlink.symlink_to(unrelated)
            with self.assertRaises(app.PlanError):
                app.save_plan("destroyed", symlink, source, force=True)
            self.assertEqual(source.read_text(), "original")
            self.assertEqual(unrelated.read_text(), "unrelated")

    def test_cli_runs_without_network_capability(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "plan.html"
            with patch("socket.socket", side_effect=AssertionError("Network is forbidden")), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(app.main([str(EXAMPLE), "--output", str(output)]), 0)
            self.assertIn("Fictional household example", output.read_text())


if __name__ == "__main__":
    unittest.main()
