"""Count reconciliation, value exclusion, and private revision-summary publication."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import plan_review as review
import private_storage as storage
import resilience_plan as app

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "fictional-household.json"
SECTIONS = {"title", "region", "reviewed_on", "contacts", "meeting_points", "household", "notes", "sources"}
COUNTS = {"added", "removed", "changed", "total"}


def fictional_plan(marker):
    """Give every value-bearing field a distinct fictional sentinel."""
    return {"schema_version": 1, "title": marker + " title", "region": marker + " region",
            "reviewed_on": "2024-02-29", "contacts": [
                {"name": marker + " name", "role": marker + " role", "contact": marker + " contact"}],
            "meeting_points": [{"label": marker + " label", "instructions": marker + " instructions"}],
            "household": [{"name": marker + " member", "needs": marker + " needs"}],
            "notes": marker + " notes", "sources": [{"title": marker + " source",
                "url": "https://example.invalid/" + marker, "verified_on": "2023-01-02"}]}


class RevisionSummaryTests(unittest.TestCase):
    def setUp(self):
        self.before = fictional_plan("FICTIONAL_BEFORE_CANARY")
        self.after = fictional_plan("FICTIONAL_AFTER_CANARY")
        self.after["reviewed_on"] = "2025-03-04"
        self.after["sources"][0]["verified_on"] = "2025-03-05"

    def assert_allowlist(self, summary):
        self.assertEqual(set(summary), {"summary_format", "plan_schema_version", "matching", "review_state", "totals", "sections"})
        self.assertIs(type(summary["summary_format"]), int)
        self.assertEqual(summary["summary_format"], 1)
        self.assertIs(type(summary["plan_schema_version"]), int)
        self.assertEqual(summary["plan_schema_version"], 1)
        self.assertEqual(summary["matching"], "ordered-index")
        self.assertEqual(summary["review_state"], "not_verified_by_tool")
        self.assertEqual(set(summary["sections"]), SECTIONS)
        for counts in [summary["totals"], *summary["sections"].values()]:
            self.assertEqual(set(counts), COUNTS)
            for count in counts.values():
                self.assertIs(type(count), int)
                self.assertGreaterEqual(count, 0)
            self.assertEqual(counts["total"], counts["added"] + counts["removed"] + counts["changed"])
        for name in COUNTS:
            self.assertEqual(summary["totals"][name], sum(section[name] for section in summary["sections"].values()))

    def test_equal_inputs_yield_zero_counts_without_review_confirmation(self):
        summary = review.summarize_revision(self.before, self.before)
        self.assert_allowlist(summary)
        self.assertEqual(summary["totals"], dict.fromkeys(COUNTS, 0))
        self.assertTrue(all(not any(values.values()) for values in summary["sections"].values()))

    def test_changed_values_dates_and_fingerprints_cannot_enter_summary(self):
        full = review.compare_plans(self.before, self.after)
        summary = review.summarize_revision(self.before, self.after)
        self.assert_allowlist(summary)
        self.assertEqual(summary["totals"], {"added": 0, "removed": 0, "changed": 14, "total": 14})
        serialized = json.dumps(summary)
        for sentinel in ["FICTIONAL_BEFORE_CANARY", "FICTIONAL_AFTER_CANARY", "2024-02-29", "2023-01-02",
                         "2025-03-04", "2025-03-05", "https://", full["before"]["sha256"], full["after"]["sha256"],
                         '"before"', '"after"', '"path"', '"sha256"', '"canonical_bytes"', '"entries"', '"changes"']:
            self.assertNotIn(sentinel, serialized)

    def test_different_plans_and_unchanged_list_sizes_with_same_patterns_match(self):
        other_before, other_after = fictional_plan("OTHER_BEFORE"), fictional_plan("OTHER_AFTER")
        other_before["reviewed_on"], other_after["reviewed_on"] = "2021-01-01", "2022-01-01"
        other_before["sources"][0]["verified_on"], other_after["sources"][0]["verified_on"] = "2021-02-02", "2022-02-02"
        # Unchanged additional entries are not disclosed as entry counts.
        extra = {"name": "Unchanged fictional extra", "role": "Unchanged fictional role", "contact": "Unchanged fictional details"}
        other_before["contacts"].append(copy.deepcopy(extra))
        other_after["contacts"].append(copy.deepcopy(extra))
        first = review.summarize_revision(self.before, self.after)
        second = review.summarize_revision(other_before, other_after)
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_counts_reconcile_with_full_review_for_nested_missing_reordered_duplicates(self):
        baseline = json.loads(EXAMPLE.read_text())
        cases = []
        changed = copy.deepcopy(baseline)
        del changed["notes"]
        del changed["sources"]  # Missing differs from a present empty list.
        changed["household"][0].pop("needs")
        changed["contacts"].append(copy.deepcopy(changed["contacts"][0]))
        cases.append((baseline, changed))
        reordered = copy.deepcopy(baseline)
        reordered["household"] = [{"name": "Fictional A", "needs": "Fictional support"}, {"name": "Fictional B"}, {"name": "Fictional B"}]
        reversed_plan = copy.deepcopy(reordered)
        reversed_plan["household"] = list(reversed(reversed_plan["household"]))
        cases.extend([(reordered, reversed_plan), (reversed_plan, reordered)])
        inserted = copy.deepcopy(reordered)
        inserted["household"].insert(1, {"name": "Fictional insertion"})
        cases.extend([(reordered, inserted), (inserted, reordered)])
        for before, after in cases:
            full = review.compare_plans(before, after)
            summary = review.summarize_revision(before, after)
            self.assert_allowlist(summary)
            for operation in ("added", "removed", "changed"):
                self.assertEqual(summary["totals"][operation], full["summary"][operation])
            for section in SECTIONS:
                records = [record for record in full["changes"] if record["path"].split("/")[1] == section]
                self.assertEqual(summary["sections"][section]["total"], len(records))
                for operation in ("added", "removed", "changed"):
                    self.assertEqual(summary["sections"][section][operation], sum(record["operation"] == operation for record in records))

    def test_summary_does_not_construct_full_report_or_fingerprints(self):
        with patch.object(review, "compare_plans", side_effect=AssertionError("Full report not permitted")), \
                patch.object(review.hashlib, "sha256", side_effect=AssertionError("Fingerprints not permitted")), \
                patch.object(review, "render_review", side_effect=AssertionError("HTML not permitted")):
            summary = review.summarize_revision(self.before, self.after)
        self.assert_allowlist(summary)

    def test_object_order_is_ignored_but_text_normalization_is_not(self):
        before = dict(reversed(list(self.before.items())))
        self.assertEqual(review.summarize_revision(self.before, before)["totals"]["total"], 0)
        after = copy.deepcopy(self.before)
        before["title"], after["title"] = "Caf\u00e9", "Cafe\u0301"
        self.assertEqual(review.summarize_revision(before, after)["sections"]["title"]["changed"], 1)

    def test_inputs_are_unchanged_and_result_contains_no_shared_values(self):
        original = copy.deepcopy((self.before, self.after))
        summary = review.summarize_revision(self.before, self.after)
        summary["sections"]["notes"]["changed"] = 99
        self.assertEqual((self.before, self.after), original)
        self.assertEqual(summary["sections"]["sources"]["changed"], 3)

    def test_both_inputs_retain_schema_and_byte_validation(self):
        invalids = [dict(self.before, schema_version=True), dict(self.before, reviewed_on="PRIVATE_DATE"),
                    dict(self.before, household=[{"name": "PRIVATE_NAME", "unsupported": "PRIVATE_VALUE"}])]
        for invalid in invalids:
            for before, after in [(invalid, self.after), (self.before, invalid)]:
                with self.assertRaises(app.PlanError) as failed:
                    review.summarize_revision(before, after)
                self.assertNotIn("PRIVATE_", str(failed.exception))
        with patch.object(review, "MAX_INPUT_BYTES", 1), self.assertRaises(app.PlanError):
            review.summarize_revision(self.before, self.after)


@unittest.skipUnless(os.name == "posix", "POSIX private revision summary workflow")
class RevisionSummaryStorageTests(unittest.TestCase):
    def setUp(self):
        self.previous = Path.cwd()
        self.temporary = tempfile.TemporaryDirectory()
        os.chdir(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(os.chdir, self.previous)
        self.before = Path("PRIVATE_BEFORE.json")
        self.after = Path("PRIVATE_AFTER.json")
        self.before.write_text(json.dumps(fictional_plan("FICTIONAL_BEFORE_CANARY")))
        self.after.write_text(json.dumps(fictional_plan("FICTIONAL_AFTER_CANARY")))
        self.original = (self.before.read_bytes(), self.after.read_bytes())
        self.output = Path("private-output/nested/PRIVATE_SUMMARY.json")

    def create(self, destination=None):
        return review.create_revision_summary(self.before, self.after, self.output if destination is None else destination)

    @contextlib.contextmanager
    def publication_operation(self, name, side_effect):
        # Inject after directory capability checks; replacing os.link earlier
        # would only test the platform-support guard, not atomic publication.
        publisher = review.publish_private_bytes
        operations = []
        def publish(*args, **kwargs):
            with patch.object(storage.os, name, side_effect=side_effect) as operation:
                operations.append(operation)
                return publisher(*args, **kwargs)
        with patch.object(review, "publish_private_bytes", side_effect=publish):
            yield
        self.assertEqual(len(operations), 1)
        self.assertTrue(operations[0].called)

    def test_atomic_private_single_file_has_no_companion_report_or_payload_output(self):
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            result = self.create()
        self.assertEqual(json.loads(self.output.read_text()), result)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.output.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.output.parent.parent.stat().st_mode), 0o700)
        self.assertEqual([p.name for p in self.output.parent.iterdir()], [self.output.name])
        for value in ("PRIVATE_BEFORE", "PRIVATE_AFTER", "PRIVATE_SUMMARY", "FICTIONAL_", self.temporary.name):
            self.assertNotIn(value, self.output.read_text())
        self.assertLess(self.output.stat().st_size, 2048)
        second = Path("private-output/another.json")
        self.create(second)
        self.assertEqual(second.read_bytes(), self.output.read_bytes())
        self.assertEqual((self.before.read_bytes(), self.after.read_bytes()), self.original)

    def test_existing_files_inputs_links_and_directories_cannot_be_replaced(self):
        self.create()
        original = self.output.read_bytes()
        with self.assertRaises(storage.StorageError):
            self.create()
        self.assertEqual(self.output.read_bytes(), original)
        for kind in ("input", "symlink", "hardlink", "directory"):
            target = self.output.parent / (kind + ".json")
            if kind == "input": target.write_bytes(self.original[0])
            elif kind == "symlink": target.symlink_to(self.before.resolve())
            elif kind == "hardlink": os.link(self.before, target)
            else: target.mkdir(mode=0o700)
            with self.subTest(kind=kind), self.assertRaises(storage.StorageError):
                self.create(target)
        source = self.output.parent / "input.json"
        with self.assertRaises(storage.StorageError):
            review.create_revision_summary(source, self.after, source)
        self.assertEqual(source.read_bytes(), self.original[0])
        self.assertEqual((self.before.read_bytes(), self.after.read_bytes()), self.original)

    def test_linked_or_permissive_parents_and_outside_paths_fail(self):
        Path("other").mkdir(mode=0o700)
        Path("private-output").symlink_to(Path("other").resolve(), target_is_directory=True)
        with self.assertRaises(storage.StorageError):
            self.create()
        self.assertEqual(list(Path("other").iterdir()), [])
        Path("private-output").unlink()
        Path("private-output").mkdir(mode=0o700)
        Path("private-output").chmod(0o755)
        with self.assertRaises(storage.StorageError):
            self.create()
        Path("private-output").chmod(0o700)
        for destination in ("elsewhere.json", "private-output/../outside.json", "private-output/summary.txt"):
            with self.subTest(destination=destination), self.assertRaises(storage.StorageError):
                self.create(destination)
        self.assertEqual(list(Path("private-output").iterdir()), [])

    def test_invalid_inputs_leave_no_output_directory(self):
        for payload in (b'{"PRIVATE_VALUE":', b'\xff', b'{"schema_version":1,"schema_version":1}',
                        b' ' * (app.MAX_INPUT_BYTES + 1)):
            self.after.write_bytes(payload)
            with self.assertRaises(app.PlanError) as failed:
                self.create()
            self.assertNotIn("PRIVATE_", str(failed.exception))
            self.assertFalse(self.output.parent.parent.exists())
        self.after.unlink()
        os.mkfifo(self.after)
        with self.assertRaises(app.PlanError):
            self.create()
        self.assertFalse(self.output.parent.parent.exists())

    def test_pending_write_or_publish_failure_cleans_owned_file(self):
        for call, failure in (("fsync", OSError("PRIVATE_ERROR")), ("link", OSError("PRIVATE_ERROR")),
                              ("fsync", KeyboardInterrupt())):
            with self.publication_operation(call, failure):
                expected = KeyboardInterrupt if isinstance(failure, KeyboardInterrupt) else storage.StorageError
                with self.assertRaises(expected) as failed:
                    self.create()
            self.assertNotIn("PRIVATE_ERROR", str(failed.exception))
            self.assertFalse(self.output.exists())
            self.assertEqual(list(self.output.parent.iterdir()), [])
            self.assertEqual((self.before.read_bytes(), self.after.read_bytes()), self.original)

    def test_competing_output_is_preserved_without_cleanup_of_unowned_file(self):
        def competing(source, destination, **kwargs):
            descriptor = kwargs["dst_dir_fd"]
            storage.write_private_bytes(descriptor, destination, b"Fictional competing output")
            raise FileExistsError("PRIVATE_RACE")
        with self.publication_operation("link", competing), self.assertRaises(storage.StorageError) as failed:
            self.create()
        self.assertNotIn("PRIVATE_RACE", str(failed.exception))
        self.assertEqual(self.output.read_bytes(), b"Fictional competing output")
        self.assertEqual([p.name for p in self.output.parent.iterdir()], [self.output.name])

    def test_complete_file_is_visible_only_at_publication(self):
        link = storage.os.link
        observed = []
        def inspect_then_link(source, destination, **kwargs):
            self.assertFalse(self.output.exists())
            descriptor = os.open(source, os.O_RDONLY, dir_fd=kwargs["src_dir_fd"])
            with os.fdopen(descriptor, "rb") as stream:
                observed.append(json.loads(stream.read()))
            return link(source, destination, **kwargs)
        with self.publication_operation("link", inspect_then_link):
            result = self.create()
        self.assertEqual(observed, [result])
        self.assertEqual(json.loads(self.output.read_text()), result)

    def test_cli_default_is_private_and_never_prints_counts_or_values(self):
        with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(app.main(["summarize-revision", str(self.before), str(self.after)]), 0)
            self.assertEqual(app.main(["summarize-revision", str(self.before), str(self.after)]), 2)
            self.assertEqual(app.main(["summarize-revision", str(self.before), str(self.after), "--force"]), 2)
            with patch.object(review, "create_revision_summary", side_effect=KeyboardInterrupt()):
                self.assertEqual(app.main(["summarize-revision", str(self.before), str(self.after), "--output", str(self.output)]), 130)
        combined = output.getvalue() + error.getvalue()
        for sentinel in ("PRIVATE_", "FICTIONAL_", self.temporary.name, '{', '"totals"', '"sections"'):
            self.assertNotIn(sentinel, combined)
        self.assertLess(len(combined), 1024)
        self.assertTrue(Path("private-output/revision-summary.json").is_file())
        self.assertFalse(self.output.exists())

    def test_direct_script_fixed_errors_and_success_without_tracebacks(self):
        arguments = [sys.executable, str(ROOT / "resilience_plan.py"), "summarize-revision", str(self.before)]
        for tail in (["PRIVATE_MISSING.json"], [str(self.after), "--PRIVATE_OPTION"]):
            completed = subprocess.run([*arguments, *tail], capture_output=True, text=True, timeout=5)
            self.assertEqual(completed.returncode, 2)
            self.assertNotIn("PRIVATE_", completed.stdout + completed.stderr)
            self.assertNotIn("Traceback", completed.stdout + completed.stderr)
            self.assertLess(len(completed.stdout + completed.stderr), 250)
        self.after.write_text('{"PRIVATE_BROKEN":')
        completed = subprocess.run([*arguments, str(self.after)], capture_output=True, text=True, timeout=5)
        self.assertEqual(completed.returncode, 2)
        self.assertNotIn("PRIVATE_", completed.stdout + completed.stderr)
        self.assertNotIn("Traceback", completed.stdout + completed.stderr)
        self.assertFalse(Path("private-output").exists())
        self.after.write_bytes(self.original[1])
        completed = subprocess.run([*arguments, str(self.after), "--output", str(self.output)], capture_output=True, text=True, timeout=5)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, "")
        self.assertNotIn("PRIVATE_", completed.stdout)
        self.assertNotIn("FICTIONAL_", self.output.read_text())
        self.assertNotIn('{', completed.stdout)


if __name__ == "__main__":
    unittest.main()
