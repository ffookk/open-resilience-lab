"""Deterministic, local comparisons of two validated schema-v1 household plans.

Lists are compared by their zero-based position. This module does not identify
people, match moved records, verify facts, or change a household review date.
"""
import hashlib
import html
import json
import os

from bundle_export import (MAX_BUNDLE_FILE_BYTES, MAX_MANIFEST_BYTES,
                           create_private_artifact_directory)
from private_storage import (StorageError, open_directory_no_links, private_parent,
                             publish_private_bytes, read_regular_bytes, require_absent)
from resilience_plan import MAX_INPUT_BYTES, PlanError, load_plan, validate_plan

FORMAT_VERSION = 1
SUMMARY_FORMAT_VERSION = 1
OPERATIONS = ("added", "removed", "changed")
PAYLOAD_NAMES = ("comparison.json", "review.html")
ARTIFACT_NAMES = frozenset((*PAYLOAD_NAMES, "manifest.json"))
SECTIONS = ("title", "region", "reviewed_on", "contacts", "meeting_points", "household", "notes", "sources")
LISTS = ("contacts", "meeting_points", "household", "sources")
MATCHING_NOTICE = ("Lists are compared by zero-based position, never by a person's name or a source URL. "
                   "Inserting, removing, or reordering entries can therefore change several positions. "
                   "Counts describe change records, not people or completed tasks.")
REVIEW_NOTICE = ("This comparison does not confirm household review, source accuracy, or emergency readiness. "
                 "Review dates remain statements from the input plans. No date or arrangement is updated.")


def _json_bytes(value, *, compact=False):
    options = {"separators": (",", ":")} if compact else {"indent": 2}
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, **options)
    return (text if compact else text + "\n").encode("utf-8")


def _snapshot(plan):
    validate_plan(plan)
    payload = _json_bytes(plan, compact=True)
    if len(payload) > MAX_INPUT_BYTES:
        raise PlanError("A comparison input exceeds the 256 KiB size limit.")
    return json.loads(payload), payload


def _pointer(path, component):
    return path + "/" + str(component).replace("~", "~0").replace("/", "~1")


def _changes(before, after, path=""):
    """Yield stable JSON Pointer records; missing subtrees are single records."""
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            location = _pointer(path, key)
            if key not in before:
                yield {"operation": "added", "path": location, "after": after[key]}
            elif key not in after:
                yield {"operation": "removed", "path": location, "before": before[key]}
            else:
                yield from _changes(before[key], after[key], location)
    elif isinstance(before, list) and isinstance(after, list):
        for index in range(max(len(before), len(after))):
            location = _pointer(path, index)
            if index >= len(before):
                yield {"operation": "added", "path": location, "after": after[index]}
            elif index >= len(after):
                yield {"operation": "removed", "path": location, "before": before[index]}
            else:
                yield from _changes(before[index], after[index], location)
    elif before != after:
        yield {"operation": "changed", "path": path, "before": before, "after": after}


def compare_plans(before, after):
    """Return a detached deterministic report without mutating either input.

    Object key order and JSON whitespace do not affect SHA-256. String contents,
    optional-field presence, array order, and duplicate list entries do affect it.
    """
    before, before_bytes = _snapshot(before)
    after, after_bytes = _snapshot(after)
    changes = list(_changes(before, after))
    summary = {operation: sum(item["operation"] == operation for item in changes)
               for operation in ("added", "removed", "changed")}
    summary.update({"total": len(changes), "identical": not changes, "sections": {
        section: sum(item["path"].split("/")[1] == section for item in changes)
        for section in SECTIONS}})

    def metadata(plan, payload):
        return {"sha256": hashlib.sha256(payload).hexdigest(), "canonical_bytes": len(payload),
                "entries": {name: len(plan.get(name, [])) for name in LISTS}}

    return {"comparison_format": FORMAT_VERSION, "plan_schema_version": 1,
            "matching": "ordered-index", "review_state": "not_verified_by_tool",
            "before": metadata(before, before_bytes), "after": metadata(after, after_bytes),
            "summary": summary, "changes": changes}


def summarize_revision(before, after):
    """Count fixed sections and operations without returning values or fingerprints.

    This intentionally does not construct a full report or identify either
    source. Equal count patterns produce the same summary, even for different
    plans. Aggregate counts can still be sensitive and are not anonymous.
    """
    before, _ = _snapshot(before)
    after, _ = _snapshot(after)
    totals = {operation: 0 for operation in (*OPERATIONS, "total")}
    sections = {section: dict(totals) for section in SECTIONS}
    for change in _changes(before, after):
        section = change["path"].split("/", 2)[1]
        operation = change["operation"]
        sections[section][operation] += 1
        sections[section]["total"] += 1
        totals[operation] += 1
        totals["total"] += 1
    return {"summary_format": SUMMARY_FORMAT_VERSION, "plan_schema_version": 1,
            "matching": "ordered-index", "review_state": "not_verified_by_tool",
            "totals": totals, "sections": sections}


def create_revision_summary(before_path, after_path, destination):
    """Publish one complete private JSON summary without a value-bearing report."""
    summary = summarize_revision(load_plan(before_path), load_plan(after_path))
    payload = _json_bytes(summary)
    try:
        with private_parent(destination, "private-output", ".json", create=True) as (parent, leaf):
            require_absent(parent, leaf)
            publish_private_bytes(parent, leaf, payload)
    except StorageError:
        raise
    except (OSError, ValueError, RuntimeError):
        raise StorageError("Unable to save the private revision summary. No existing output was overwritten.") from None
    return summary


def render_review(report):
    """Render a report generated by compare_plans as inert, self-contained HTML."""
    escape = lambda value: html.escape(str(value), quote=True)

    def value(item, side):
        if side not in item:
            return '<p class="absent">Not present</p>'
        content = item[side]
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, sort_keys=True, indent=2)
        return '<pre dir="auto">' + escape(content) + '</pre>'

    rows = []
    for index, item in enumerate(report["changes"], 1):
        rows.append('<article aria-labelledby="change-' + str(index) + '"><h3 id="change-' + str(index)
                    + '">' + escape(item["operation"].capitalize()) + ': <code>' + escape(item["path"])
                    + '</code></h3><div class="values"><section aria-label="Before value"><h4>Before</h4>'
                    + value(item, "before") + '</section><section aria-label="After value"><h4>After</h4>'
                    + value(item, "after") + '</section></div></article>')
    summary = report["summary"]
    sections = ''.join('<tr><th scope="row"><code>' + escape(section) + '</code></th><td>'
                       + escape(summary["sections"][section]) + '</td></tr>' for section in SECTIONS)
    snapshots = ''.join('<section><h3>' + label + '</h3><p>Canonical SHA-256: <code>'
                        + escape(report[key]["sha256"]) + '</code></p><p>Canonical UTF-8 bytes: '
                        + escape(report[key]["canonical_bytes"]) + '</p><dl>'
                        + ''.join('<dt>' + escape(name) + '</dt><dd>' + escape(report[key]["entries"][name])
                                  + '</dd>' for name in LISTS) + '</dl></section>'
                        for key, label in (("before", "Before"), ("after", "After")))
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer"><title>Private plan revision review</title><style>
*{box-sizing:border-box}body{max-width:1100px;margin:auto;padding:24px;font:16px/1.6 system-ui,sans-serif;color:#182b36;background:#f5f7f8}
h1{line-height:1.25}h2,h3,h4{break-after:avoid}article,.notice,.snapshots{padding:16px;border:1px solid #59747a;background:white;margin:16px 0}
h3,h4{margin:0 0 8px}article{break-inside:avoid}p,pre,code,dt,dd{overflow-wrap:anywhere}pre{white-space:pre-wrap;font:inherit;margin:0}
.values,.snapshots{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.values section{min-width:0}.absent{font-style:italic}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:6px;border-bottom:1px solid #cbd5d9}dt{font-weight:bold}dd{margin-left:0}
.skip-link{position:absolute;top:-100px}.skip-link:focus{top:8px;background:white;color:#182b36;padding:8px}:focus-visible{outline:3px solid currentColor;outline-offset:3px}
@media(max-width:640px){body{padding:12px}.values,.snapshots{grid-template-columns:1fr}h1{font-size:1.7rem}}
@media print{@page{margin:15mm}body{padding:0;background:white;font-size:10pt;max-width:none}.skip-link{display:none}:focus-visible{outline:none}pre,p{orphans:3;widows:3}}
@media(forced-colors:active){body,article,.notice,.snapshots{color:CanvasText;background:Canvas}article,.notice,.snapshots,th,td{border-color:CanvasText}}
</style></head><body><a class="skip-link" href="#changes">Skip to changes</a>
<header><h1>Private plan revision review</h1><p>Comparison format 1 · Plan schema 1</p></header>
<p class="notice">Keep this report, its JSON, input plans, and printouts private. Removed and replaced values remain visible here.
The report is not encrypted or redacted. No scripts, browser storage, or external resources are included.</p>
<p>''' + REVIEW_NOTICE + '</p><h2>Comparison rules</h2><p>' + MATCHING_NOTICE + '''</p>
<p>Paths use JSON Pointer notation. Object keys are visited in sorted order; list positions start at zero.
Adding or removing a complete field or trailing list entry produces one record for that subtree.
Absent optional fields differ from explicitly empty lists. Text is compared exactly, without Unicode normalization.</p>
<h2>Summary</h2><p>''' + ('No content differences.' if summary['identical'] else 'Content differences found.') + ''' Total records: ''' + escape(summary['total']) + '; added: ' + escape(summary['added']) + '; removed: ' + escape(summary['removed']) + '; changed: ' + escape(summary['changed']) + '''.</p>
<table><caption>Change records by plan section</caption><thead><tr><th scope="col">Section</th><th scope="col">Records</th></tr></thead><tbody>''' + sections + '''</tbody></table>
<h2>Input fingerprints</h2><p>These digests identify canonical JSON content, not authorship, confidentiality, factual correctness, or completed review.
Whitespace and object key order do not affect the digest. No input filenames or generation timestamps are recorded.</p><div class="snapshots">''' + snapshots + '''</div>
<main id="changes" tabindex="-1"><h2>Before and after values</h2>''' + (''.join(rows) or '<p>No change records.</p>') + '''</main>
<footer><p>Open Resilience Lab · Local comparison only. Source URLs are inert text and are never fetched.
Use the browser Print menu and preview pagination before printing.</p></footer></body></html>
'''


def _artifacts(before, after):
    report = compare_plans(before, after)
    payloads = {"comparison.json": _json_bytes(report), "review.html": render_review(report).encode("utf-8")}
    if any(len(value) > MAX_BUNDLE_FILE_BYTES for value in payloads.values()):
        raise PlanError("A comparison artifact exceeds the supported size limit.")
    manifest = {"review_format": FORMAT_VERSION, "files": {
        name: {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
        for name, payload in payloads.items()}}
    return report, payloads, _json_bytes(manifest)


def create_review(before_path, after_path, destination):
    """Validate both bounded inputs before exclusively creating private artifacts."""
    report, payloads, manifest = _artifacts(load_plan(before_path), load_plan(after_path))
    create_private_artifact_directory(payloads, manifest, destination)
    return report


def verify_review(before_path, after_path, directory):
    """Read-only exact verification against both plans and the current format.

    The manifest is not trusted to select files. Fixed names and byte caps apply
    before reading; edited, missing, reordered, or extra artifacts are rejected.
    """
    _, payloads, manifest = _artifacts(load_plan(before_path), load_plan(after_path))
    expected = {**payloads, "manifest.json": manifest}
    try:
        with open_directory_no_links(directory) as descriptor:
            if set(os.listdir(descriptor)) != ARTIFACT_NAMES:
                raise StorageError("The review is incomplete or contains unexpected files.")
            for name in (*PAYLOAD_NAMES, "manifest.json"):
                limit = MAX_MANIFEST_BYTES if name == "manifest.json" else MAX_BUNDLE_FILE_BYTES
                if read_regular_bytes(descriptor, name, limit) != expected[name]:
                    raise StorageError("The review does not match both input plans and the supported comparison format.")
            if set(os.listdir(descriptor)) != ARTIFACT_NAMES:
                raise StorageError("Review entries changed during verification.")
    except StorageError:
        raise
    except (OSError, ValueError, RuntimeError):
        raise StorageError("Unable to verify this review safely. Check its files and permissions locally.") from None
    return True
