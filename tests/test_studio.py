"""Parity, local draft behavior, inert exports, and private blank-editor creation.

JavaScript checks require Node on PATH; their explicit skip is not parity evidence.
Normal studio generation and use need no Node or third-party Python dependency.
"""
import contextlib
import copy
from datetime import date
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import plan_studio as studio
import private_storage as storage
import resilience_plan as app

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


def fixture():
    return {"schema_version": 1, "title": "Fictional studio plan", "region": "Fictional region", "reviewed_on": "2024-02-29",
            "contacts": [{"name": "Example contact", "role": "Agreed role", "contact": "Example contact details"}],
            "meeting_points": [{"label": "Example meeting", "instructions": "Agreed example instructions"}]}


def node(operation, data=None):
    script = '''const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const api = require('./studio/core.js')(input.policy);
const data = input.data;
const output = (() => {''' + operation + '''})();
process.stdout.write(JSON.stringify(output));'''
    result = subprocess.run([NODE, "-e", script], input=json.dumps({"policy": studio.studio_policy(), "data": data}),
                            text=True, capture_output=True, cwd=ROOT, timeout=20)
    if result.returncode:
        raise AssertionError("The JavaScript check failed; inspect the synthetic development case locally.")
    return json.loads(result.stdout)


class InspectHTML(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags, self.scripts, self.styles, self.csp = [], [], [], None
        self.current = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs); self.tags.append((tag, attrs))
        if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy": self.csp = attrs["content"]
        if tag in ("script", "style"):
            self.current = [attrs, ""]
            (self.scripts if tag == "script" else self.styles).append(self.current)

    def handle_data(self, data):
        if self.current is not None: self.current[1] += data

    def handle_endtag(self, tag):
        if tag in ("script", "style"): self.current = None


@unittest.skipUnless(NODE, "Node is unavailable: JavaScript parity/state checks were NOT run")
class StudioJavaScriptTests(unittest.TestCase):
    def test_schema_and_unicode_parity_against_python(self):
        plans = [fixture()]
        def changed(path, value):
            plan = fixture(); target = plan
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value; plans.append(plan)
        for value in (True, 1.0, "1", None, 0, 2): changed(["schema_version"], value)
        for value in ("", " ", chr(0x85), chr(0xfeff), "\n\t", "safe\nline\ttab", "bad\rreturn", "bad" + chr(127), chr(0xd800), chr(0xdc00), chr(0x1f642) * 120, chr(0x1f642) * 121): changed(["title"], value)
        for value in ("0000-01-01", "0001-01-01", "9999-12-31", "1900-02-29", "2000-02-29", "2024-2-29", "2024-04-31", "2024-02-29\n", None): changed(["reviewed_on"], value)
        for path in (["contacts"], ["meeting_points"], ["household"], ["sources"]):
            for value in (None, {}, "", [], True): changed(path, value)
        for key in ("household", "sources"): changed([key], [])
        changed(["household"], [{"name": "Example member"}]); changed(["household"], [{"name": "Example member", "needs": ""}])
        changed(["notes"], ""); changed(["notes"], "Example notes\nSecond line"); changed(["notes"], "x" * 4001)
        changed(["contacts", 0, "role"], "x" * 201); changed(["meeting_points", 0, "instructions"], "x" * 2001)
        changed(["contacts"], fixture()["contacts"] * 21); changed(["meeting_points"], fixture()["meeting_points"] * 11)
        changed(["unsupported"], "Example"); changed(["contacts", 0, "unsupported"], "Example")
        del_required = fixture(); del del_required["region"]; plans.append(del_required)
        plans.extend([None, [], "text"])
        expected = []
        for plan in plans:
            try: app.validate_plan(plan); expected.append(True)
            except app.PlanError: expected.append(False)
        actual = node("return data.map(text => {try {api.importJSON(text); return true;} catch (_) {return false;}});", [json.dumps(plan, ensure_ascii=True) for plan in plans])
        self.assertEqual(actual, expected)
        self.assertGreater(sum(actual), 5)
        self.assertGreater(len(actual) - sum(actual), 40)

    def test_source_url_parity_including_ports_delimiters_and_brackets(self):
        urls = ["https://example.invalid", "HTTPS://example.invalid:443/path", "https://example.invalid:",
                "https://example.invalid:0", "https://example.invalid:65535", "https://example.invalid:65536", "https://example.invalid:-1",
                "https://example.invalid:00123", "https://example.invalid:1.0", "https://example.invalid:" + chr(0x661),
                "https://example.invalid?", "https://example.invalid#", "https://example.invalid?#", "https://example.invalid?q=x", "https://example.invalid#x",
                "https://user@example.invalid", "https://:password@example.invalid", "https://@example.invalid", "https:///path", "http://example.invalid",
                "https://example.invalid\\path", "https://example.invalid/path with space", "https://example.invalid/" + chr(0x85),
                "https://example.invalid/" + chr(0xfeff), "https://example.invalid/%20", "https://example.invalid/" + chr(0x1f642),
                "https://example" + chr(0xff0f) + "invalid", "https://[::1]", "https://[::1]:443", "https://[::1]:65536", "https://[::1]junk",
                "https://prefix[::1]", "https://[127.0.0.1]", "https://[1:2:3:4:5:6:7:8]", "https://[1:2:3:4:5:6:7]", "https://[::ffff:192.0.2.1]",
                "https://[::ffff:192.000.2.1]", "https://[fe80::1%zone]", "https://[fe80::1%]", "https://[v1.example]", "https://[V1.example]",
                "https://[v1.]", "https://example.invalid:port", "https://example.invalid:443:444", "https://[]", "https://example.invalid?x#"]
        cases, expected = [], []
        for url in urls:
            plan = fixture(); plan["sources"] = [{"title": "Example source", "url": url, "verified_on": "2024-02-29"}]
            cases.append(json.dumps(plan))
            try: app.validate_plan(plan); expected.append(True)
            except app.PlanError: expected.append(False)
        actual = node("return data.map(text => {try {api.importJSON(text); return true;} catch (_) {return false;}});", cases)
        self.assertEqual([i for i, pair in enumerate(zip(actual, expected)) if pair[0] != pair[1]], [])

    def test_strict_json_rejects_duplicates_lexical_float_versions_and_syntax(self):
        valid = json.dumps(fixture())
        invalid = [valid.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1'),
                   valid.replace('"schema_version": 1', '"schema_version": 1, "schema_\\u0076ersion": 1'),
                   valid.replace('"name": "Example contact"', '"name": "Example contact", "name": "Duplicate"'),
                   valid.replace('"schema_version": 1', '"schema_version": 1e0'), valid.replace('"schema_version": 1', '"schema_version": 1.0'),
                   valid + " garbage", valid[:-1] + ",}", "\ufeff" + valid, '[' * 50 + '0' + ']' * 50,
                   valid.replace('"region": "Fictional region"', '"region": NaN'), valid.replace('"schema_version": 1', '"schema_version": Infinity')]
        accepted = node("return data.map(text => {try {api.importJSON(text); return true;} catch (_) {return false;}});", invalid)
        self.assertEqual(accepted, [False] * len(invalid))
        self.assertEqual(node("return api.importJSON(data);", valid), fixture())

    def test_import_bytes_rejects_invalid_utf8_bom_and_size(self):
        result = node('''const base = new TextEncoder().encode(data);
const samples = [new Uint8Array([0xff]), new Uint8Array([0xef,0xbb,0xbf,...base]), new Uint8Array(api.policy.max_bytes + 1)];
return {valid:api.importBytes(base), invalid:samples.map(raw => {try {api.importBytes(raw); return false;} catch (_) {return true;}})};''', json.dumps(fixture()))
        self.assertEqual(result["valid"], fixture()); self.assertEqual(result["invalid"], [True] * 3)

    def test_roundtrip_preserves_optional_absence_empty_lists_and_all_text(self):
        plan = fixture(); plan.update(household=[{"name": "Example member"}, {"name": "Second member", "needs": "Line one\n\tLine two "}],
                                     notes="  Example notes\n", sources=[{"title": "Example source", "url": "https://example.invalid?#", "verified_on": "0001-01-01"}])
        plan["title"] = chr(0xfeff) + "Title " + chr(0x1f642)
        variants = [fixture(), dict(fixture(), household=[], sources=[]), plan]
        outputs = node("return data.map(text => api.exportJSON(api.importJSON(text)));", [json.dumps(p) for p in variants])
        for original, output in zip(variants, outputs):
            self.assertEqual(json.loads(output), original); app.validate_plan(json.loads(output))

    def test_state_reorders_whole_entries_and_preserves_optional_fields(self):
        plan = fixture(); plan["contacts"].append({"name": "Second contact", "role": "Second role", "contact": "Second details"})
        result = node('''const d = new api.Draft(data); d.move('contacts',0,1); d.optional(['household'],true,[]); d.add('household');
d.set(['household',0,'name'],'Example member'); d.optional(['household',0,'needs'],true,'Example need');
d.optional(['notes'],true,'Example note'); const edited=api.clone(d.plan); d.optional(['notes'],false,''); d.remove('contacts',1);
return {edited, final:d.plan, dirty:d.dirty, outside:d.move('contacts',0,-1)};''', plan)
        self.assertEqual(result["edited"]["contacts"], list(reversed(plan["contacts"])))
        self.assertEqual(result["final"]["household"], [{"name": "Example member", "needs": "Example need"}])
        self.assertNotIn("notes", result["final"]); self.assertTrue(result["dirty"]); self.assertFalse(result["outside"])

    def test_state_import_failure_never_replaces_draft(self):
        result = node('''const d = new api.Draft(data); d.set(['title'],'Edited example'); const before=api.clone(d.plan);
try {d.import('{"schema_version":true}');} catch (_) {}
return {before,after:d.plan,dirty:d.dirty};''', fixture())
        self.assertEqual(result["before"], result["after"]); self.assertTrue(result["dirty"])

    def test_export_request_requires_explicit_save_confirmation_and_new_edits_invalidate_it(self):
        result = node('''const d = new api.Draft(data); d.set(['title'],'Edited example'); d.requestJSON(); const dirtyAfterRequest=d.dirty;
d.set(['region'],'Changed example'); const stale=d.confirmSaved(); d.requestJSON(); const confirmed=d.confirmSaved();
return {dirtyAfterRequest,stale,confirmed,dirtyAfterConfirmation:d.dirty};''', fixture())
        self.assertEqual(result, {"dirtyAfterRequest": True, "stale": False, "confirmed": True, "dirtyAfterConfirmation": False})

    def test_blank_reset_and_list_limits_remain_incomplete_until_review(self):
        result = node('''const d = new api.Draft(data); for(let n=0;n<30;n++)d.add('meeting_points');
const maximum=d.plan.meeting_points.length; d.reset(); let exported=false; try{d.requestJSON();exported=true;}catch(_){}
return {maximum,plan:d.plan,errors:api.validate(d.plan).length,dirty:d.dirty,exported};''', fixture())
        self.assertEqual(result["maximum"], 10); self.assertEqual(result["plan"]["reviewed_on"], "")
        self.assertGreater(result["errors"], 0); self.assertFalse(result["dirty"]); self.assertFalse(result["exported"])

    def test_printable_exports_escape_text_preserve_data_and_have_no_scripts_or_external_resources(self):
        plan = fixture(); attack = '</script><img src="https://example.invalid" onerror="alert(1)"> &'
        plan["title"] = attack; plan["meeting_points"][0]["instructions"] = attack + "\nSecond line"
        plan.update(household=[{"name":"Example member", "needs":"Example support"}], notes="Example private note", sources=[{"title":"Example source","url":"https://example.invalid/source","verified_on":"2024-01-01"}])
        outputs = node("return [api.exportHTML(data), api.exportHTML(data,true)];", plan)
        for output in outputs:
            parsed = InspectHTML(output)
            self.assertFalse(parsed.scripts)
            self.assertFalse(any(tag == "img" or any(key in attrs for key in ("src", "href", "onerror")) for tag, attrs in parsed.tags))
            self.assertIn("style-src 'sha256-" + studio.digest(parsed.styles[0][1]) + "'", parsed.csp)
            self.assertIn("&lt;img", output); self.assertIn("Second line", output)
        self.assertIn("Example private note", outputs[0]); self.assertIn("https://example.invalid/source", outputs[0]); self.assertIn("Example support", outputs[0])
        self.assertNotIn("Example private note", outputs[1]); self.assertEqual(outputs[1].count("<article>"), 2)

    def test_invalid_draft_cannot_export_any_format(self):
        result = node("return [()=>api.exportJSON(api.blank()),()=>api.exportHTML(api.blank()),()=>api.exportHTML(api.blank(),true)].map(run=>{try{run();return false;}catch(_){return true;}});")
        self.assertEqual(result, [True] * 3)


class StudioDocumentTests(unittest.TestCase):
    def test_blank_document_is_offline_and_hashes_authorize_only_emitted_assets(self):
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            rendered = studio.render_studio()
        parsed = InspectHTML(rendered)
        self.assertEqual(len(parsed.scripts), 3)
        for _, script in parsed.scripts: self.assertIn("'sha256-" + studio.digest(script) + "'", parsed.csp)
        self.assertIn("'sha256-" + studio.digest(parsed.styles[0][1]) + "'", parsed.csp)
        self.assertIn("connect-src 'none'", parsed.csp); self.assertNotIn("unsafe-inline", parsed.csp); self.assertNotIn("unsafe-eval", parsed.csp)
        self.assertFalse(any(any(key in attrs for key in ("src", "action")) or "href" in attrs and not attrs["href"].startswith("#") for _, attrs in parsed.tags))
        self.assertNotIn("Fictional studio plan", rendered)
        for _, script in parsed.scripts:
            for forbidden in ("localStorage", "sessionStorage", "indexedDB", "fetch(", "XMLHttpRequest", "document.cookie", "innerHTML", "eval("):
                self.assertNotIn(forbidden, script)

    def test_static_controls_are_labeled_and_js_parses_when_node_available(self):
        parsed = InspectHTML(studio.render_studio())
        labels = {attrs.get("for") for tag, attrs in parsed.tags if tag == "label"}
        self.assertIn("import-json", labels)
        self.assertTrue(any(attrs.get("role") == "status" for _, attrs in parsed.tags))
        if NODE:
            for name in ("core.js", "ui.js"):
                self.assertEqual(subprocess.run([NODE, "--check", str(studio.ASSET_ROOT / name)], capture_output=True).returncode, 0)


@unittest.skipUnless(os.name == "posix", "POSIX private storage workflow")
class StudioStorageTests(unittest.TestCase):
    def setUp(self):
        self.previous = Path.cwd(); self.directory = tempfile.TemporaryDirectory(); os.chdir(self.directory.name)
        self.addCleanup(self.directory.cleanup); self.addCleanup(os.chdir, self.previous)
        self.output = Path("private-output/nested/studio.html")

    def test_blank_studio_publishes_privately_without_network(self):
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")): studio.write_studio(self.output)
        self.assertEqual(self.output.read_text(), studio.render_studio())
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.output.parent.stat().st_mode), 0o700)
        self.assertFalse(list(Path("private-output").rglob(".pending-*")))

    def test_existing_outputs_and_hardlink_aliases_are_not_overwritten(self):
        studio.write_studio(self.output); before = self.output.read_bytes()
        alias = self.output.with_name("alias.html"); os.link(self.output, alias)
        for destination in (self.output, alias):
            with self.assertRaises(storage.StorageError): studio.write_studio(destination)
        self.assertEqual(self.output.read_bytes(), before); self.assertEqual(alias.read_bytes(), before)

    def test_destination_boundaries_and_parent_links_are_refused(self):
        for destination in ("studio.html", "private-output/../studio.html", "private-output/file.json", "private-output/PRIVATE\x00.html"):
            with self.assertRaises(storage.StorageError): studio.write_studio(destination)
        Path("other").mkdir(); Path("private-output").symlink_to(Path("other").resolve(), target_is_directory=True)
        with self.assertRaises(storage.StorageError): studio.write_studio(self.output)
        self.assertEqual(list(Path("other").iterdir()), [])

    def test_existing_permissive_directory_is_refused(self):
        Path("private-output").mkdir(mode=0o755); Path("private-output").chmod(0o755)
        with self.assertRaises(storage.StorageError): studio.write_studio(self.output)
        self.assertEqual(list(Path("private-output").iterdir()), [])

    def test_write_failure_or_cancellation_leaves_no_partial_studio(self):
        for error in (OSError("PRIVATE_STORAGE_DETAIL"), KeyboardInterrupt()):
            with patch.object(storage.os, "fsync", side_effect=error):
                with self.assertRaises((storage.StorageError, KeyboardInterrupt)) as result: studio.write_studio(self.output)
            self.assertNotIn("PRIVATE_STORAGE_DETAIL", str(result.exception)); self.assertFalse(self.output.exists())
            self.assertFalse(list(Path("private-output").rglob(".pending-*")))

    def test_cli_rejects_private_arguments_without_echo_and_preserves_existing_commands(self):
        for args in (["studio", "--output", "PRIVATE_MARKER.html"], ["studio", "--force", "PRIVATE_MARKER"], ["studio", "PRIVATE_MARKER.json"]):
            with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(app.main(args), 2)
            self.assertNotIn("PRIVATE_MARKER", output.getvalue() + errors.getvalue())
        with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(app.main(["studio"]), 0)
        self.assertTrue(Path("private-output/plan-studio.html").is_file())
        with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(app.main([str(ROOT / "examples/fictional-household.json"), "--check"]), 0)


if __name__ == "__main__":
    unittest.main()
