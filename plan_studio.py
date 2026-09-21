"""Generate a blank, self-contained household plan editor with private local storage."""
import base64
import hashlib
import html
import json
from pathlib import Path
from urllib.parse import urlsplit

from private_storage import StorageError, private_parent, publish_private_bytes, require_absent
from resilience_plan import MAX_INPUT_BYTES

ASSET_ROOT = Path(__file__).resolve().parent / "studio"
EXPORT_CSS = """*{box-sizing:border-box}body{max-width:1000px;margin:auto;padding:24px;color:#183631;background:white;font:16px/1.5 system-ui,sans-serif}h1,h2,h3,p,footer{overflow-wrap:anywhere}h1{line-height:1.2}h2{font-size:1.2em;border-bottom:1px solid #aac1b5;padding-bottom:6px}h3{font-size:1em;margin:0 0 6px}h1,h3,p,footer{white-space:pre-wrap}article{border:1px solid #b6cbbf;padding:12px;margin:8px 0;break-inside:avoid}footer{font-size:.8em;margin-top:16px}.cards .entries{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.cards article{border-style:dashed;margin:0}.cards{font-size:14px}@media(max-width:600px){.cards .entries{grid-template-columns:1fr}body{padding:12px}}@media print{@page{margin:10mm}body{padding:0;font-size:11pt}.cards{font-size:10pt}.cards .entries{gap:5mm}h2,h3{break-after:avoid}p{orphans:2;widows:2}}"""


def digest(value):
    return base64.b64encode(hashlib.sha256(value.encode("utf-8")).digest()).decode("ascii")


def studio_policy():
    """Public fixed configuration, also the entrypoint for Node parity tests.

    Python's supported releases differ in bracketed authority checks. Record the
    generating runtime's behavior without embedding input, paths, or environment.
    """
    try:
        urlsplit("https://prefix[::1]").port
        strict_brackets = False
    except ValueError:
        strict_brackets = True
    return {"max_bytes": MAX_INPUT_BYTES, "limits": {"title": 120, "region": 120, "notes": 4000},
            "whitespace": [code for code in range(0x3001) if chr(code).isspace()],
            "strict_brackets": strict_brackets, "export_css": EXPORT_CSS,
            "export_csp": "default-src 'none'; script-src 'none'; style-src 'sha256-" + digest(EXPORT_CSS)
            + "'; connect-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'"}


def render_studio():
    """Return a blank studio; household input is never accepted or embedded here."""
    css = (ASSET_ROOT / "studio.css").read_text(encoding="utf-8").strip()
    core = (ASSET_ROOT / "core.js").read_text(encoding="utf-8").strip()
    ui = (ASSET_ROOT / "ui.js").read_text(encoding="utf-8").strip()
    configuration = "globalThis.PLAN_STUDIO_POLICY = " + json.dumps(studio_policy(), ensure_ascii=True, separators=(",", ":")) + ";"
    scripts = [configuration, core, ui]
    csp = ("default-src 'none'; script-src " + " ".join("'sha256-" + digest(script) + "'" for script in scripts)
           + "; style-src 'sha256-" + digest(css) + "'; connect-src 'none'; img-src 'none'; font-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'")
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="''' + html.escape(csp, quote=True) + '''">
<meta name="referrer" content="no-referrer"><title>Offline Household Plan Studio</title><style>''' + css + '''</style></head>
<body><a href="#plan-form" class="skip-link">Skip to plan editor</a>
<header><p class="eyebrow">OPEN RESILIENCE LAB · LOCAL TO THIS TAB</p><h1>Household Plan Studio</h1>
<p>Write down arrangements your household has already agreed. Edit locally, review the format, and export the files you choose to keep.</p>
<p>This blank draft contains no household data and makes no assumption that a review has taken place.</p></header>
<main class="shell"><div class="privacy"><strong>Private working space, not encrypted storage.</strong>
Enter only necessary information on a trusted device. No network requests, browser storage, cookies, telemetry, or automatic saves are used.
Imported files, downloads, printouts, and visible previews may contain private data. Browser downloads use your browser's destination and permissions.
Do not publish a real plan. This tool gives no medical advice, independent factual review, or safety certification.</div>
<div class="toolbar"><div><label for="import-json">Import local JSON (up to 256 KiB)</label><input id="import-json" type="file" accept=".json,application/json"></div>
<button id="toggle-preview" type="button" class="secondary" aria-controls="preview-panel" aria-expanded="true">Hide live preview</button><button id="reset" type="button" class="danger">Reset to blank draft</button></div>
<noscript><p class="privacy">Enable JavaScript locally to use this editor, or use the Python wizard. No draft is saved automatically.</p></noscript>
<nav aria-label="Editor sections"><a id="review-link" href="#review-save">Review and save</a><a href="#section-basics">Plan details</a><a href="#section-contacts">Contacts</a><a href="#section-meeting_points">Meeting arrangements</a><a href="#section-household">Household</a><a href="#section-notes">Notes</a><a href="#section-sources">Sources</a><a href="#preview-panel">Preview</a></nav>
<div class="layout"><div id="editor-column"><section id="review-save" class="validation-panel" tabindex="-1" aria-labelledby="validation-title"><h2 id="validation-title">Review and save</h2>
<p id="draft-status" role="status" aria-live="polite"></p><p id="validation-status" role="status" aria-live="polite"></p>
<div class="downloads"><button id="validate" type="button">Validate and show issues</button><button id="first-issue" type="button" class="secondary">Go to first issue</button><button id="export-json" type="button" disabled>Download editable JSON</button><button id="export-html" type="button" class="secondary" disabled>Download full plan HTML</button><button id="export-cards" type="button" class="secondary" disabled>Download printable cards</button><button id="confirm-saved" type="button" class="secondary" disabled>I saved the JSON</button></div>
<p class="fine">A download request cannot confirm a disk save. Check your JSON file before marking it saved. HTML exports do not clear unsaved edits. Closing or refreshing this page can lose work; the browser may not always show an unsaved warning.</p>
<p id="operation-status" role="status" aria-live="polite"></p><div id="validation-errors" tabindex="-1" hidden></div></section>
<form id="plan-form" tabindex="-1" autocomplete="off" novalidate></form></div>
<aside id="preview-panel" class="preview-panel" aria-labelledby="preview-title"><h2 id="preview-title">Live draft preview</h2>
<p>Incomplete fields can appear here. Export buttons are enabled only after format checks pass. Source URLs remain inert text.</p><label for="preview-section">Preview section</label><select id="preview-section"><option value="all">All sections</option><option value="0">Contacts</option><option value="1">Meeting arrangements</option><option value="2">Household</option><option value="3">Notes</option><option value="4">Sources</option></select><label class="toggle"><input id="compact-preview" type="checkbox">Compact preview cards</label><label class="toggle"><input id="large-preview" type="checkbox">Larger preview text</label><div id="preview-content"></div><details id="json-inspector"><summary>Inspect draft JSON</summary><p class="hint">Read-only current draft; it may be incomplete. This view is not a saved file.</p><label for="draft-json">Current draft JSON</label><textarea id="draft-json" readonly rows="12" spellcheck="false"></textarea></details></aside></div></main>
<footer>All entered dates and sources remain user supplied. Keep the editable JSON for later changes. Arbitrary HTML import is not supported. No export occurs on closing this page.</footer>
''' + "".join("<script>" + script + "</script>" for script in scripts) + "</body></html>\n"


def write_studio(destination):
    """Exclusively publish a complete blank editor under private-output on POSIX."""
    try:
        content = render_studio().encode("utf-8")
        with private_parent(destination, "private-output", ".html", create=True) as (parent, leaf):
            require_absent(parent, leaf)
            publish_private_bytes(parent, leaf, content)
    except StorageError:
        raise
    except (OSError, ValueError, RuntimeError):
        raise StorageError("Unable to create the blank studio safely. Check its local files and private destination.") from None
