import contextlib
import copy
import hashlib
from html.parser import HTMLParser
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

import bundle_export as bundles
import plan_review as review
import private_storage as storage
import resilience_plan as app

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples' / 'fictional-household.json'


class ReviewModelTests(unittest.TestCase):
    def setUp(self):
        self.before = json.loads(EXAMPLE.read_text())
        self.after = copy.deepcopy(self.before)

    def compare(self):
        return review.compare_plans(self.before, self.after)

    def test_equal_plans_have_no_changes_or_implied_review(self):
        report = self.compare()
        self.assertEqual(report['changes'], [])
        self.assertEqual(report['summary']['total'], 0)
        self.assertTrue(report['summary']['identical'])
        self.assertEqual(report['before'], report['after'])
        self.assertEqual(report['review_state'], 'not_verified_by_tool')
        self.assertEqual(report['matching'], 'ordered-index')
        self.assertNotIn('reviewed_on', report['before'])
        self.assertNotIn('generated_at', report)

    def test_hash_definition_and_key_order_are_stable(self):
        self.after = dict(reversed(list(self.after.items())))
        self.after['contacts'][0] = dict(reversed(list(self.after['contacts'][0].items())))
        report = self.compare()
        payload = json.dumps(self.before, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
        self.assertEqual(report['before']['sha256'], hashlib.sha256(payload).hexdigest())
        self.assertEqual(report['before']['canonical_bytes'], len(payload))
        self.assertEqual(report['before'], report['after'])
        self.assertEqual(report['changes'], [])

    def test_scalar_and_nested_changes_have_complete_values_and_section_counts(self):
        self.after['title'] = 'Fictional revision'
        self.after['reviewed_on'] = '2026-09-21'
        self.after['contacts'][0]['role'] = 'Fictional revised role'
        report = self.compare()
        self.assertEqual(report['changes'], [
            {'operation': 'changed', 'path': '/contacts/0/role', 'before': self.before['contacts'][0]['role'], 'after': 'Fictional revised role'},
            {'operation': 'changed', 'path': '/reviewed_on', 'before': '2026-09-20', 'after': '2026-09-21'},
            {'operation': 'changed', 'path': '/title', 'before': self.before['title'], 'after': 'Fictional revision'},
        ])
        self.assertEqual(report['summary']['changed'], 3)
        self.assertEqual(sum(report['summary']['sections'].values()), 3)
        self.assertEqual(report['summary']['sections']['reviewed_on'], 1)
        self.assertNotEqual(report['before']['sha256'], report['after']['sha256'])

    def test_missing_optional_list_differs_from_present_empty_list(self):
        del self.before['sources']
        report = self.compare()
        self.assertEqual(report['changes'], [{'operation': 'added', 'path': '/sources', 'after': []}])
        self.assertEqual(report['before']['entries']['sources'], 0)
        self.assertEqual(report['after']['entries']['sources'], 0)
        self.assertNotEqual(report['before']['sha256'], report['after']['sha256'])

    def test_removed_and_added_subtrees_are_single_records(self):
        del self.after['notes']
        self.after['sources'].append({'title': 'Fictional source', 'url': 'https://example.invalid/guide', 'verified_on': '2026-09-21'})
        report = self.compare()
        self.assertEqual(report['summary']['removed'], 1)
        self.assertEqual(report['summary']['added'], 1)
        self.assertEqual(report['changes'][0], {'operation': 'removed', 'path': '/notes', 'before': self.before['notes']})
        self.assertEqual(report['changes'][1], {'operation': 'added', 'path': '/sources/0', 'after': self.after['sources'][0]})

    def test_reorder_does_not_infer_identity_or_moves(self):
        self.before['household'] = [{'name': 'Fictional A', 'needs': 'Fictional A support'}, {'name': 'Fictional B'}]
        self.after['household'] = list(reversed(copy.deepcopy(self.before['household'])))
        report = self.compare()
        self.assertEqual([(item['operation'], item['path']) for item in report['changes']], [
            ('changed', '/household/0/name'), ('removed', '/household/0/needs'),
            ('changed', '/household/1/name'), ('added', '/household/1/needs')])
        self.assertEqual(report['summary']['total'], 4)

    def test_duplicate_entries_and_middle_insertion_use_positions(self):
        item = {'name': 'Duplicate fictional entry'}
        self.before['household'] = [item, copy.deepcopy(item)]
        self.after['household'] = [copy.deepcopy(item), {'name': 'Inserted fictional entry'}, copy.deepcopy(item)]
        report = self.compare()
        self.assertEqual([(item['operation'], item['path']) for item in report['changes']], [
            ('changed', '/household/1/name'), ('added', '/household/2')])
        self.after['household'] = [copy.deepcopy(item)]
        report = self.compare()
        self.assertEqual(report['changes'], [{'operation': 'removed', 'path': '/household/1', 'before': item}])

    def test_lexical_text_is_not_normalized_and_unicode_is_preserved(self):
        self.before['title'] = 'Caf\u00e9'
        self.after['title'] = 'Cafe\u0301'
        report = self.compare()
        self.assertEqual(len(report['changes']), 1)
        self.assertNotEqual(report['before']['sha256'], report['after']['sha256'])
        self.assertIn('Cafe\u0301', review.render_review(report))

    def test_report_and_inputs_do_not_share_mutable_values(self):
        self.after['household'].append({'name': 'Fictional addition'})
        before, after = copy.deepcopy(self.before), copy.deepcopy(self.after)
        report = self.compare()
        self.assertEqual(self.before, before)
        self.assertEqual(self.after, after)
        report['changes'][0]['after']['name'] = 'Changed report only'
        self.assertEqual(self.after, after)
        self.after['household'][-1]['name'] = 'Changed input only'
        self.assertEqual(report['changes'][0]['after']['name'], 'Changed report only')

    def test_invalid_schema_dates_controls_and_nested_fields_are_rejected(self):
        invalids = [dict(self.after, schema_version=True), dict(self.after, reviewed_on='YYYY-MM-DD'),
                    dict(self.after, notes='PRIVATE_VALUE\x00'), dict(self.after, sources=[{'title': 'PRIVATE_VALUE'}]),
                    dict(self.after, household=[{'name': 'PRIVATE_VALUE', 'unknown': True}])]
        for bad in invalids:
            with self.subTest(), self.assertRaises(app.PlanError) as failed:
                review.compare_plans(self.before, bad)
            self.assertNotIn('PRIVATE_VALUE', str(failed.exception))
        with self.assertRaises(app.PlanError):
            review.compare_plans(invalids[0], self.after)

    def test_direct_api_applies_utf8_byte_limit_after_validation(self):
        # Valid character lengths can still exceed the byte cap in UTF-8.
        plan = copy.deepcopy(self.before)
        marker = chr(0x1f642)
        plan['meeting_points'] = [{'label': 'Fictional meeting', 'instructions': marker * 2000} for _ in range(10)]
        plan['household'] = [{'name': 'Fictional member', 'needs': marker * 1000} for _ in range(20)]
        plan['sources'] = [{'title': 'Fictional source', 'url': 'https://example.invalid/' + marker * 1900,
                            'verified_on': '2026-09-20'} for _ in range(20)]
        app.validate_plan(plan)
        with self.assertRaises(app.PlanError) as failed:
            review.compare_plans(self.before, plan)
        self.assertNotIn(marker, str(failed.exception))

    def test_html_escapes_every_changed_value_without_active_resources(self):
        self.after['notes'] = '</pre><script>PRIVATE_VALUE</script><img src="https://example.invalid/pixel">\n& "quotes"'
        self.after['contacts'][0]['name'] = '<svg onload="alert(1)">'
        self.after['sources'] = [{'title': '<a href="https://example.invalid/">Link</a>', 'url': 'https://example.invalid/<tag>', 'verified_on': '2026-09-21'}]
        document = review.render_review(self.compare())
        self.assertIn('&lt;script&gt;PRIVATE_VALUE&lt;/script&gt;', document)
        self.assertIn('&lt;svg onload=&quot;alert(1)&quot;&gt;', document)
        self.assertIn('https://example.invalid/&lt;tag&gt;', document)
        self.assertIn("default-src 'none'", document)
        self.assertIn('No date or arrangement is updated.', document)
        self.assertIn('zero-based position', document)
        class Elements(HTMLParser):
            def __init__(self):
                super().__init__()
                self.tags = []
            def handle_starttag(self, tag, attrs):
                self.tags.append((tag, dict(attrs)))
        elements = Elements()
        elements.feed(document)
        for tag, attrs in elements.tags:
            self.assertNotIn(tag, {'script', 'iframe', 'form', 'img', 'svg', 'link', 'object', 'embed', 'base', 'audio', 'video'})
            self.assertFalse(any(name.startswith('on') or name in {'src', 'action'} for name in attrs))
            if 'href' in attrs:
                self.assertTrue(attrs['href'].startswith('#'))
        self.assertNotIn('localStorage', document)
        self.assertNotIn('url(', document)
        self.assertNotIn('@import', document)


@unittest.skipUnless(os.name == 'posix', 'POSIX private review workflow')
class ReviewStorageTests(unittest.TestCase):
    def setUp(self):
        self.previous = Path.cwd()
        self.directory = tempfile.TemporaryDirectory()
        os.chdir(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(os.chdir, self.previous)
        self.before = Path('PRIVATE_BEFORE.json')
        self.after = Path('PRIVATE_AFTER.json')
        self.before.write_bytes(EXAMPLE.read_bytes())
        revised = json.loads(EXAMPLE.read_text())
        revised['notes'] = 'Fictional changed note.'
        self.after.write_text(json.dumps(revised), encoding='utf-8')
        self.input_bytes = (self.before.read_bytes(), self.after.read_bytes())
        self.output = Path('private-output/revision')

    def create(self):
        return review.create_review(self.before, self.after, self.output)

    def verify(self):
        return review.verify_review(self.before, self.after, self.output)

    def test_complete_deterministic_private_export_and_offline_verification(self):
        with patch('socket.socket', side_effect=AssertionError('Network is forbidden')):
            report = self.create()
            self.assertTrue(self.verify())
        self.assertEqual({p.name for p in self.output.iterdir()}, review.ARTIFACT_NAMES)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.output.parent.stat().st_mode), 0o700)
        self.assertEqual(json.loads((self.output / 'comparison.json').read_text()), report)
        manifest = json.loads((self.output / 'manifest.json').read_text())
        for name in review.PAYLOAD_NAMES:
            payload = (self.output / name).read_bytes()
            self.assertEqual(manifest['files'][name], {'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)})
        second = Path('private-output/another')
        review.create_review(self.before, self.after, second)
        for path in self.output.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(path.read_bytes(), (second / path.name).read_bytes())
            self.assertNotIn(b'PRIVATE_BEFORE', path.read_bytes())
            self.assertNotIn(b'PRIVATE_AFTER', path.read_bytes())
            self.assertNotIn(self.directory.name.encode(), path.read_bytes())
        self.assertEqual((self.before.read_bytes(), self.after.read_bytes()), self.input_bytes)

    def test_formatting_only_changes_to_inputs_still_verify(self):
        self.create()
        for path in (self.before, self.after):
            data = json.loads(path.read_text())
            path.write_text(json.dumps(dict(reversed(list(data.items()))), indent=4), encoding='utf-8')
        self.assertTrue(self.verify())

    def test_mutated_or_reversed_inputs_cannot_verify(self):
        self.create()
        with self.assertRaises(storage.StorageError):
            review.verify_review(self.after, self.before, self.output)
        self.after.write_bytes(self.before.read_bytes())
        with self.assertRaises(storage.StorageError):
            self.verify()

    def test_json_reordering_tampering_and_missing_extra_entries_fail(self):
        self.create()
        for name in review.ARTIFACT_NAMES:
            path = self.output / name
            original = path.read_bytes()
            path.write_text('PRIVATE_TAMPER_VALUE')
            with self.subTest(name=name), self.assertRaises(storage.StorageError) as failed:
                self.verify()
            self.assertNotIn('PRIVATE_TAMPER_VALUE', str(failed.exception))
            path.unlink()
            with self.assertRaises(storage.StorageError):
                self.verify()
            path.write_bytes(original)
        path = self.output / 'comparison.json'
        path.write_text(json.dumps(json.loads(path.read_text()), indent=4))
        with self.assertRaises(storage.StorageError):
            self.verify()
        (self.output / 'PRIVATE_EXTRA_FILE').write_text('PRIVATE_CONTENT')
        with self.assertRaises(storage.StorageError) as failed:
            self.verify()
        self.assertNotIn('PRIVATE_EXTRA_FILE', str(failed.exception))

    def test_manifest_cannot_redirect_verifier_to_another_path(self):
        self.create()
        (self.output / 'manifest.json').write_text('{"files":{"../PRIVATE_OUTSIDE":{}}}')
        with patch.object(review, 'read_regular_bytes', wraps=storage.read_regular_bytes) as reads:
            with self.assertRaises(storage.StorageError):
                self.verify()
        self.assertEqual([call.args[1] for call in reads.call_args_list], [*review.PAYLOAD_NAMES, 'manifest.json'])

    def test_output_existing_files_links_and_inputs_are_never_replaced(self):
        self.create()
        snapshot = {p.name: p.read_bytes() for p in self.output.iterdir()}
        with self.assertRaises(storage.StorageError):
            self.create()
        self.assertEqual({p.name: p.read_bytes() for p in self.output.iterdir()}, snapshot)
        for kind in ('input', 'symlink', 'hardlink', 'directory'):
            destination = Path('private-output/' + kind)
            if kind == 'input':
                destination.write_bytes(self.before.read_bytes())
            elif kind == 'symlink':
                destination.symlink_to(self.before.resolve())
            elif kind == 'hardlink':
                os.link(self.before, destination)
            else:
                destination.mkdir(mode=0o700)
            with self.subTest(kind=kind), self.assertRaises(storage.StorageError):
                review.create_review(self.before, self.after, destination)
        local_input = Path('private-output/input')
        with self.assertRaises(storage.StorageError):
            review.create_review(local_input, self.after, local_input)
        self.assertEqual((self.before.read_bytes(), self.after.read_bytes()), self.input_bytes)
        self.assertEqual(local_input.read_bytes(), self.input_bytes[0])

    def test_parent_links_traversal_and_permissive_directories_are_rejected(self):
        Path('other').mkdir(mode=0o700)
        Path('private-output').symlink_to(Path('other').resolve(), target_is_directory=True)
        with self.assertRaises(storage.StorageError):
            self.create()
        self.assertEqual(list(Path('other').iterdir()), [])
        Path('private-output').unlink()
        Path('private-output').mkdir(mode=0o755)
        Path('private-output').chmod(0o755)
        with self.assertRaises(storage.StorageError):
            self.create()
        Path('private-output').chmod(0o700)
        for destination in ('private-output/../elsewhere', 'outside/review'):
            with self.subTest(destination=destination), self.assertRaises(storage.StorageError):
                review.create_review(self.before, self.after, destination)

    def test_verifier_rejects_linked_nonregular_and_oversized_artifacts(self):
        self.create()
        target = self.output / 'comparison.json'
        original = target.read_bytes()
        for kind in ('symlink', 'hardlink', 'directory', 'fifo', 'oversize'):
            target.unlink()
            external = Path('external.json')
            external.write_bytes(original)
            if kind == 'symlink': target.symlink_to(external.resolve())
            elif kind == 'hardlink': os.link(external, target)
            elif kind == 'directory': target.mkdir()
            elif kind == 'fifo': os.mkfifo(target)
            else:
                with target.open('wb') as stream:
                    stream.truncate(review.MAX_BUNDLE_FILE_BYTES + 1)
            with self.subTest(kind=kind), self.assertRaises(storage.StorageError):
                self.verify()
            target.rmdir() if kind == 'directory' else target.unlink()
            target.write_bytes(original)
            external.unlink()
        Path('linked-review').symlink_to(self.output.resolve(), target_is_directory=True)
        with self.assertRaises(storage.StorageError):
            review.verify_review(self.before, self.after, 'linked-review')
        manifest = self.output / 'manifest.json'
        with manifest.open('wb') as stream:
            stream.truncate(review.MAX_MANIFEST_BYTES + 1)
        with self.assertRaises(storage.StorageError):
            self.verify()

    def test_invalid_bounded_inputs_produce_no_output(self):
        invalids = [b'{"PRIVATE_VALUE":', b'\xff', b'{"schema_version":1,"schema_version":1}',
                    b' ' * (app.MAX_INPUT_BYTES + 1), b'[' * 2000 + b']' * 2000]
        for payload in invalids:
            self.after.write_bytes(payload)
            with self.subTest(), self.assertRaises(app.PlanError) as failed:
                self.create()
            self.assertNotIn('PRIVATE_VALUE', str(failed.exception))
            self.assertFalse(self.output.parent.exists())
        self.after.unlink()
        os.mkfifo(self.after)
        with self.assertRaises(app.PlanError):
            self.create()
        self.assertFalse(self.output.parent.exists())

    def test_manifest_is_last_and_failures_clean_only_owned_files(self):
        writer = bundles.write_private_bytes
        seen = []
        def record(parent, name, payload, **kwargs):
            seen.append(name)
            self.assertFalse((self.output / 'manifest.json').exists())
            return writer(parent, name, payload, **kwargs)
        with patch.object(bundles, 'write_private_bytes', side_effect=record):
            self.create()
        self.assertEqual(seen, list(review.PAYLOAD_NAMES))
        other_output = Path('private-output/failure')
        for failure in (OSError('PRIVATE_ERROR'), KeyboardInterrupt()):
            def interrupt(parent, name, payload, **kwargs):
                if name == 'review.html':
                    raise failure
                return writer(parent, name, payload, **kwargs)
            expected = storage.StorageError if isinstance(failure, OSError) else KeyboardInterrupt
            with patch.object(bundles, 'write_private_bytes', side_effect=interrupt), self.assertRaises(expected) as failed:
                review.create_review(self.before, self.after, other_output)
            self.assertNotIn('PRIVATE_ERROR', str(failed.exception))
            self.assertFalse(other_output.exists())
        def concurrent(parent, name, payload, **kwargs):
            if name == 'review.html':
                storage.write_private_bytes(parent, 'unrelated.txt', b'KEEP')
                raise OSError('PRIVATE_ERROR')
            return writer(parent, name, payload, **kwargs)
        with patch.object(bundles, 'write_private_bytes', side_effect=concurrent), self.assertRaises(storage.StorageError):
            review.create_review(self.before, self.after, other_output)
        self.assertEqual({p.name for p in other_output.iterdir()}, {'unrelated.txt'})
        self.assertEqual((other_output / 'unrelated.txt').read_bytes(), b'KEEP')

    def test_failed_manifest_publication_cleans_new_directory(self):
        with patch.object(bundles, 'publish_private_bytes', side_effect=OSError('PRIVATE_FAILURE')):
            with self.assertRaises(storage.StorageError) as failed:
                self.create()
        self.assertNotIn('PRIVATE_FAILURE', str(failed.exception))
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.output.parent.iterdir()), [])
        self.assertEqual((self.before.read_bytes(), self.after.read_bytes()), self.input_bytes)

    def test_verification_is_read_only_even_on_failure(self):
        self.create()
        snapshot = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.output.iterdir()}
        with patch.object(bundles, 'create_private_artifact_directory', side_effect=AssertionError('Write is forbidden')):
            self.assertTrue(self.verify())
            with self.assertRaises(storage.StorageError):
                review.verify_review(self.before, self.before, self.output)
        self.assertEqual({p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.output.iterdir()}, snapshot)

    def test_cli_messages_are_bounded_and_never_include_values_or_paths(self):
        with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(app.main(['compare', str(self.before), str(self.after), '--output', str(self.output)]), 0)
            self.assertEqual(app.main(['verify-review', str(self.before), str(self.after), str(self.output)]), 0)
            self.assertEqual(app.main(['compare', str(self.before), str(self.after), '--output', str(self.output)]), 2)
            self.assertEqual(app.main(['compare', '--PRIVATE_OPTION']), 2)
            with patch.object(review, 'create_review', side_effect=KeyboardInterrupt()):
                self.assertEqual(app.main(['compare', str(self.before), str(self.after), '--output', 'private-output/PRIVATE_PATH']), 130)
        combined = output.getvalue() + error.getvalue()
        for value in ('PRIVATE_BEFORE', 'PRIVATE_AFTER', 'PRIVATE_OPTION', 'PRIVATE_PATH', self.directory.name, str(self.output)):
            self.assertNotIn(value, combined)
        self.assertLess(len(combined), 1500)

    def test_real_cli_invalid_input_exits_without_traceback_or_private_values(self):
        self.after.write_text('{"PRIVATE_CONTENT":')
        for command in ('compare', 'verify-review'):
            for source in (str(self.after), 'PRIVATE_MISSING.json'):
                arguments = [command, str(self.before), source]
                arguments += ['--output', str(self.output)] if command == 'compare' else [str(self.output)]
                result = subprocess.run([sys.executable, str(ROOT / 'resilience_plan.py'), *arguments],
                                        capture_output=True, text=True)
                with self.subTest(command=command, source=source):
                    self.assertEqual(result.returncode, 2)
                    combined = result.stdout + result.stderr
                    self.assertNotIn('Traceback', combined)
                    self.assertNotIn('PRIVATE_', combined)
                    self.assertNotIn(self.directory.name, combined)
                    self.assertLess(len(combined), 250)
                    self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
