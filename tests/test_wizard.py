import contextlib
import getpass
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
import warnings

import private_storage as storage
import resilience_plan as app


def minimal_answers():
    return ["yes", "Fictional plan", "Fictional region", "2026-09-20", "1",
            "Example contact", "Agreed role", "Example contact details", "1",
            "Example meeting", "Agreed fictional instructions", "0", "", "0", "yes"]


def reader(answers):
    values = iter(answers)
    def read(_prompt):
        try:
            value = next(values)
        except StopIteration:
            raise EOFError from None
        if isinstance(value, BaseException):
            raise value
        return value
    return read


@unittest.skipUnless(os.name == "posix", "POSIX private storage workflow")
class WizardTests(unittest.TestCase):
    def setUp(self):
        self.previous = Path.cwd()
        self.directory = tempfile.TemporaryDirectory()
        os.chdir(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(os.chdir, self.previous)
        self.messages = []
        self.output = "private-input/nested/plan.json"

    def create(self, answers=None):
        return app.run_wizard(self.output, read_answer=reader(minimal_answers() if answers is None else answers), report=self.messages.append)

    def test_complete_plan_is_valid_and_saved_with_private_permissions(self):
        with patch("socket.socket", side_effect=AssertionError("Network is forbidden")):
            plan = self.create()
        self.assertEqual(app.load_plan(self.output), plan)
        self.assertNotIn("notes", plan)
        self.assertEqual(plan["household"], [])
        self.assertEqual(plan["sources"], [])
        self.assertEqual(stat.S_IMODE(Path(self.output).stat().st_mode), 0o600)
        for name in ("private-input", "private-input/nested"):
            self.assertEqual(stat.S_IMODE(Path(name).stat().st_mode), 0o700)
        self.assertNotIn("Example contact details", "\n".join(self.messages))

    def test_retries_invalid_date_counts_and_empty_text_without_echo(self):
        answers = ["yes", "", "Fictional plan", "Fictional region", "PRIVATE_INVALID_DATE", "2026-09-20",
                   "9" * 5000, "0", "1", "Example contact", "", "Agreed role", "Example details", "1",
                   "Example meeting", "Example instructions", "0", "", "0", "yes"]
        plan = self.create(answers)
        self.assertEqual(plan["reviewed_on"], "2026-09-20")
        self.assertEqual(len(plan["contacts"]), 1)
        self.assertNotIn("PRIVATE_INVALID_DATE", "\n".join(self.messages))
        self.assertNotIn("9" * 100, "\n".join(self.messages))

    def test_optional_members_notes_and_sources_are_validated(self):
        answers = minimal_answers()[:11] + ["1", "Example member", "Example support needs", "Example notes", "1",
                                            "Example source", "https://example.invalid:PRIVATE_VALUE/path",
                                            "https://example.invalid/reference", "2026-09-20", "yes"]
        plan = self.create(answers)
        self.assertEqual(plan["household"][0]["needs"], "Example support needs")
        self.assertEqual(plan["notes"], "Example notes")
        self.assertEqual(plan["sources"][0]["url"], "https://example.invalid/reference")
        self.assertNotIn("PRIVATE_VALUE", "\n".join(self.messages))

    def test_eof_interrupt_and_cancel_leave_no_plan_or_directory(self):
        for answers in ([], minimal_answers()[:7], minimal_answers()[:-1], [KeyboardInterrupt()], ["/cancel"], ["no"]):
            with self.subTest(answer_count=len(answers)), self.assertRaises(app.WizardCancelled):
                self.create(answers)
            self.assertEqual(list(Path.cwd().iterdir()), [])

    def test_declining_final_confirmation_does_not_save(self):
        with self.assertRaises(app.WizardCancelled):
            self.create(minimal_answers()[:-1] + ["no"])
        self.assertEqual(list(Path.cwd().iterdir()), [])

    def test_existing_plan_is_rejected_before_prompting(self):
        self.create()
        before = Path(self.output).read_bytes()
        read = Mock(side_effect=AssertionError("Must reject before prompting"))
        with self.assertRaises(app.PlanError):
            app.run_wizard(self.output, read_answer=read)
        read.assert_not_called()
        self.assertEqual(Path(self.output).read_bytes(), before)

    def test_traversal_wrong_extension_and_outside_paths_are_rejected(self):
        for destination in ("plan.json", "private-input/../plan.json", "private-input/plan.txt", "private-input"):
            with self.subTest(destination=destination), self.assertRaises(app.PlanError):
                app.run_wizard(destination, read_answer=Mock(side_effect=AssertionError("Must not prompt")))
        self.assertEqual(list(Path.cwd().iterdir()), [])

    def test_symlink_parent_leaf_and_hardlinked_leaf_are_not_followed(self):
        Path("other").mkdir(mode=0o700)
        Path("private-input").symlink_to(Path("other").resolve(), target_is_directory=True)
        with self.assertRaises(app.PlanError):
            self.create()
        Path("private-input").unlink()
        Path("private-input").mkdir(mode=0o700)
        target = Path("other/keep.json")
        target.write_text("UNCHANGED")
        for link_type in ("symlink", "hardlink"):
            leaf = Path("private-input/linked.json")
            leaf.symlink_to(target.resolve()) if link_type == "symlink" else os.link(target, leaf)
            with self.assertRaises(app.PlanError):
                app.run_wizard(leaf, read_answer=reader(minimal_answers()), report=self.messages.append)
            self.assertEqual(target.read_text(), "UNCHANGED")
            leaf.unlink()

    def test_existing_permissive_private_directory_is_refused(self):
        Path("private-input").mkdir(mode=0o755)
        Path("private-input").chmod(0o755)
        with self.assertRaises(app.PlanError):
            self.create()
        self.assertEqual(list(Path("private-input").iterdir()), [])

    def test_competing_destination_is_never_replaced(self):
        publish = storage.publish_private_bytes
        def compete(parent, name, payload):
            storage.write_private_bytes(parent, name, b"OTHER_WRITER")
            return publish(parent, name, payload)
        with patch.object(storage, "publish_private_bytes", side_effect=compete), self.assertRaises(app.PlanError):
            self.create()
        self.assertEqual(Path(self.output).read_bytes(), b"OTHER_WRITER")
        self.assertEqual([p.name for p in Path(self.output).parent.iterdir()], ["plan.json"])

    def test_write_failure_cleans_pending_file_without_echoing_error(self):
        with patch.object(storage.os, "fsync", side_effect=OSError("PRIVATE_ERROR")), self.assertRaises(app.PlanError) as error:
            self.create()
        self.assertNotIn("PRIVATE_ERROR", str(error.exception))
        self.assertFalse(Path(self.output).exists())
        self.assertFalse(list(Path("private-input").rglob("*.json")))
        self.assertFalse(list(Path("private-input").rglob(".pending-*")))

    def test_cli_cancellation_and_no_terminal_are_safe(self):
        for effect, expected in ((app.WizardCancelled(), 130), (app.PlanError("A trusted terminal is required."), 2)):
            with patch.object(app, "run_wizard", side_effect=effect), contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as error:
                self.assertEqual(app.main(["wizard", "--output", "private-input/PRIVATE_PATH.json"]), expected)
            self.assertEqual(out.getvalue(), "")
            self.assertNotIn("PRIVATE_PATH", error.getvalue())
        with patch.object(app.sys, "stdin", io.StringIO()), patch.object(app.sys, "stderr", io.StringIO()):
            with self.assertRaises(app.PlanError):
                app._read_private_answer("Fixed prompt: ")
        self.assertFalse(Path("private-input").exists())

    def test_unusable_terminal_is_rejected_without_echo(self):
        closed = io.StringIO()
        closed.close()
        broken = Mock()
        broken.isatty.side_effect = OSError("PRIVATE_TERMINAL_ERROR")
        healthy = Mock()
        healthy.isatty.return_value = True
        for name in ("stdin", "stderr"):
            for terminal in (closed, broken):
                with self.subTest(stream=name), patch.object(app.sys, "stdin", healthy), patch.object(app.sys, "stderr", healthy):
                    with patch.object(app.sys, name, terminal), self.assertRaises(app.PlanError) as error:
                        app._read_private_answer("Fixed prompt: ")
                self.assertNotIn("PRIVATE_TERMINAL_ERROR", str(error.exception))
        with patch.object(app.sys, "stdin", healthy), patch.object(app.sys, "stderr", healthy):
            with patch.object(getpass, "getpass", side_effect=OSError("PRIVATE_TERMINAL_ERROR")), self.assertRaises(app.PlanError) as error:
                app._read_private_answer("Fixed prompt: ")
        self.assertNotIn("PRIVATE_TERMINAL_ERROR", str(error.exception))
        self.assertFalse(Path("private-input").exists())

    def test_echoing_getpass_fallback_is_refused(self):
        terminal = Mock()
        terminal.isatty.return_value = True
        def fallback(*_args, **_kwargs):
            warnings.warn("Fallback would echo", getpass.GetPassWarning)
            raise AssertionError("The echoing fallback must not proceed")
        with patch.object(app.sys, "stdin", terminal), patch.object(app.sys, "stderr", terminal), patch.object(getpass, "getpass", side_effect=fallback):
            with self.assertRaises(app.PlanError):
                app._read_private_answer("Fixed prompt: ")


if __name__ == "__main__":
    unittest.main()
