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

    def test_example_validates_and_generates_english_content(self):
        document = app.render_plan(app.load_plan(EXAMPLE))
        self.assertIn("<html lang=\"en\">", document)
        self.assertIn("<h2>Contacts</h2>", document)
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


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.previous_directory = Path.cwd()
        self.workspace = tempfile.TemporaryDirectory()
        os.chdir(self.workspace.name)
        self.addCleanup(self.workspace.cleanup)
        self.addCleanup(os.chdir, self.previous_directory)

    def run_cli(self, arguments, expected=0):
        with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(app.main(arguments), expected)
        return output.getvalue() + errors.getvalue()

    def test_init_creates_an_unreviewed_draft_with_private_permissions(self):
        message = self.run_cli(["init"])
        output = Path(app.TEMPLATE_PATH)
        draft = json.loads(output.read_text())
        self.assertEqual(draft["reviewed_on"], "YYYY-MM-DD")
        self.assertEqual(draft["sources"], [])
        self.assertIn("after household review", message)
        self.assertIn("intentionally fails", message)
        with self.assertRaises(app.PlanError):
            app.load_plan(output)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(output.parent.stat().st_mode), 0o700)

    def test_edited_template_generates_using_legacy_cli(self):
        self.run_cli(["template"])
        # Replacing the placeholders with the fictional fixture simulates local editing.
        Path(app.TEMPLATE_PATH).write_text(EXAMPLE.read_text(), encoding="utf-8")
        self.run_cli([app.TEMPLATE_PATH])
        self.assertIn("Fictional household example", Path("private-output/emergency-plan.html").read_text())

    def test_overwrite_requires_force_and_only_allows_an_unchanged_template(self):
        self.run_cli(["init"])
        before = Path(app.TEMPLATE_PATH).read_bytes()
        self.run_cli(["init"], expected=2)
        self.assertEqual(Path(app.TEMPLATE_PATH).read_bytes(), before)
        self.run_cli(["init", "--force"])
        self.assertEqual(Path(app.TEMPLATE_PATH).read_bytes(), before)
        private_content = '{"notes": "DO_NOT_ECHO_PRIVATE_DATA"}'
        Path(app.TEMPLATE_PATH).write_text(private_content)
        message = self.run_cli(["init", "--force"], expected=2)
        self.assertNotIn("DO_NOT_ECHO", message)
        self.assertEqual(Path(app.TEMPLATE_PATH).read_text(), private_content)

    def test_destination_rejects_source_files_parent_traversal_and_other_directories(self):
        Path("resilience_plan.py").write_text("source file")
        for destination in ("resilience_plan.py", "examples/sample.json", "household.json", "private-input",
                            "private-input/../household.json", "private-input/source.py"):
            with self.subTest(destination=destination):
                self.run_cli(["init", "--output", destination, "--force"], expected=2)
        self.assertEqual(Path("resilience_plan.py").read_text(), "source file")
        self.assertFalse(Path("household.json").exists())
        self.assertFalse(Path("examples").exists())

    def test_nested_template_directories_are_private(self):
        output = Path("private-input/nested/another/draft.json")
        self.run_cli(["init", "--output", str(output)])
        self.assertEqual(output.read_text(), app.template_document())
        if os.name == "posix":
            for directory in (output.parent, output.parent.parent, Path("private-input")):
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)

    @unittest.skipUnless(os.name == "posix", "POSIX link behavior")
    def test_linked_private_directory_cannot_escape_into_another_location(self):
        Path("unrelated").mkdir()
        Path("private-input").symlink_to(Path("unrelated").resolve(), target_is_directory=True)
        self.run_cli(["init", "--force"], expected=2)
        self.assertEqual(list(Path("unrelated").iterdir()), [])

    @unittest.skipUnless(os.name == "posix", "POSIX link behavior")
    def test_nested_directory_and_output_links_are_rejected(self):
        Path("private-input").mkdir()
        Path("unrelated").mkdir()
        Path("private-input/nested").symlink_to(Path("unrelated").resolve(), target_is_directory=True)
        self.run_cli(["init", "--output", "private-input/nested/draft.json", "--force"], expected=2)
        target = Path("unrelated/original.json")
        for exists in (False, True):
            if exists:
                target.write_text("original")
            link = Path(app.TEMPLATE_PATH)
            link.symlink_to(target.resolve())
            self.run_cli(["init", "--force"], expected=2)
            self.assertTrue(link.is_symlink())
            link.unlink()
        self.assertEqual(target.read_text(), "original")
        self.assertFalse(Path("unrelated/draft.json").exists())

    @unittest.skipUnless(os.name == "posix", "POSIX link behavior")
    def test_force_refuses_hardlinked_template(self):
        self.run_cli(["init"])
        os.link(app.TEMPLATE_PATH, "other.json")
        self.run_cli(["init", "--force"], expected=2)
        self.assertEqual(Path("other.json").read_text(), app.template_document())

    def test_cli_argument_errors_never_echo_private_values(self):
        for arguments in (["init", "--DO_NOT_ECHO_PRIVATE_DATA"],
                          ["--DO_NOT_ECHO_PRIVATE_DATA"],
                          ["init", "--output", "private-input/DO_NOT_ECHO_PRIVATE_DATA\x00.json"],
                          ["init", "--output"]):
            message = self.run_cli(arguments, expected=2)
            self.assertNotIn("DO_NOT_ECHO_PRIVATE_DATA", message)
            self.assertNotIn(self.workspace.name, message)

    def test_init_requires_no_network(self):
        from unittest.mock import patch
        with patch("socket.socket", side_effect=AssertionError("Network is forbidden")):
            self.run_cli(["init"])


if __name__ == "__main__":
    unittest.main()
