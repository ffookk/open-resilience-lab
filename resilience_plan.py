#!/usr/bin/env python3
"""Generate a local, printable household plan. Python standard library only."""
from __future__ import annotations

import argparse
from datetime import date
import html
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

MAX_INPUT_BYTES = 256 * 1024
TEMPLATE_PATH = "private-input/household.json"


class PlanError(ValueError):
    """An intentionally data-free message that is safe to show in a terminal."""


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's normal error includes supplied values, possibly private paths.
        raise PlanError("Invalid command arguments. Use --help for usage.")


def template_document():
    """An editable draft; never invent a household review or a verified source."""
    plan = {
        "schema_version": 1,
        "title": "[Enter a plan title]",
        "region": "[Enter the applicable region]",
        "reviewed_on": "YYYY-MM-DD",
        "contacts": [{
            "name": "[Enter a contact name]",
            "role": "[Enter the agreed role]",
            "contact": "[Enter contact details locally]",
        }],
        "meeting_points": [{
            "label": "[Enter a meeting arrangement label]",
            "instructions": "[Enter instructions agreed with your household]",
        }],
        "household": [],
        "notes": "Draft only, not a ready-to-use emergency plan: replace all placeholders and enter the actual household review date after reviewing the plan together.",
        "sources": [],
    }
    return json.dumps(plan, ensure_ascii=False, indent=2) + "\n"


def _object(value, required, optional=()):
    if not isinstance(value, dict):
        raise PlanError("Expected an object in the plan.")
    if not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise PlanError("The plan has missing or unsupported fields. See the example schema.")


def _text(value, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise PlanError("A text field is empty, has the wrong type, or exceeds its length limit.")
    if any((ord(c) < 32 and c not in "\n\t") or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise PlanError("A text field contains unsupported control characters.")


def _date(value):
    _text(value, 10)
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        raise PlanError("Dates must be valid calendar dates in YYYY-MM-DD format.") from None


def _items(value, minimum=0, maximum=20):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise PlanError("A list has the wrong type or an unsupported number of entries.")


def validate_plan(plan):
    """Validate the complete schema without echoing potentially private data."""
    _object(plan, ("schema_version", "title", "region", "reviewed_on", "contacts", "meeting_points"),
            ("household", "notes", "sources"))
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise PlanError("Only schema_version 1 is supported.")
    _text(plan["title"], 120)
    _text(plan["region"], 120)
    _date(plan["reviewed_on"])
    _items(plan["contacts"], 1)
    for item in plan["contacts"]:
        _object(item, ("name", "role", "contact"))
        for key in ("name", "role", "contact"):
            _text(item[key], 200)
    _items(plan["meeting_points"], 1, 10)
    for item in plan["meeting_points"]:
        _object(item, ("label", "instructions"))
        _text(item["label"], 120)
        _text(item["instructions"], 2000)
    _items(plan.get("household", []))
    for item in plan.get("household", []):
        _object(item, ("name",), ("needs",))
        _text(item["name"], 120)
        if "needs" in item:
            _text(item["needs"], 1000)
    if "notes" in plan:
        _text(plan["notes"], 4000)
    _items(plan.get("sources", []))
    for item in plan.get("sources", []):
        _object(item, ("title", "url", "verified_on"))
        _text(item["title"], 200)
        _text(item["url"], 2000)
        try:
            address = urlsplit(item["url"])
            valid_url = (address.scheme == "https" and bool(address.hostname)
                         and address.username is None and address.password is None
                         and not address.query and not address.fragment
                         and not any(c.isspace() for c in item["url"]) and "\\" not in item["url"])
        except ValueError:
            valid_url = False
        if not valid_url:
            raise PlanError("Source URLs must use HTTPS without credentials, queries, or fragments.")
        _date(item["verified_on"])
    return plan


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PlanError("Duplicate JSON fields are not supported.")
        result[key] = value
    return result


def load_plan(path):
    try:
        with Path(path).open("rb") as stream:
            payload = stream.read(MAX_INPUT_BYTES + 1)
    except (OSError, ValueError):
        raise PlanError("Unable to read the input file.") from None
    if len(payload) > MAX_INPUT_BYTES:
        raise PlanError("Input exceeds the 256 KiB size limit.")
    try:
        plan = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise PlanError("Input must be a valid UTF-8 JSON document.") from None
    return validate_plan(plan)


def render_plan(plan, *, large_text=False, compact=False):
    validate_plan(plan)
    presentation_style = []
    if compact:
        presentation_style.append('article{padding:8px;margin:6px 0}h2{margin-top:18px}body{line-height:1.4}')
    if large_text:
        presentation_style.append('body{font-size:20px}@media print{body{font-size:14pt}}')
    escape = lambda value: html.escape(value, quote=True)
    cards = lambda entries: "".join(
        '<article><h3>' + escape(title) + '</h3><p>' + escape(body) + '</p></article>'
        for title, body in entries
    )
    contacts = cards((item["name"] + " · " + item["role"], item["contact"]) for item in plan["contacts"])
    meetings = cards((item["label"], item["instructions"]) for item in plan["meeting_points"])
    household = cards((item["name"], item.get("needs", "Not provided")) for item in plan.get("household", []))
    sources = cards((item["title"], item["url"] + "\nEntered review date: " + item["verified_on"])
                    for item in plan.get("sources", []))
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer">
<title>''' + escape(plan["title"]) + '''</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:32px;color:#182b36;background:#f5f7f8;line-height:1.6}
h1{line-height:1.25}h2{margin-top:30px;border-bottom:2px solid #59747a;padding-bottom:5px}h3{margin:0 0 6px}article{background:white;border:1px solid #cbd5d9;border-radius:8px;padding:16px;margin:12px 0;break-inside:avoid}
p{white-space:pre-wrap;overflow-wrap:anywhere;margin:0 0 8px}.notice{border-left:4px solid #59747a;padding:12px;background:#e7eff1}footer{font-size:.9rem;margin-top:32px}
@media(max-width:600px){body{padding:16px}h1{font-size:1.7rem}}
@media print{@page{margin:15mm}body{background:white;padding:0;max-width:none;font-size:11pt}article{border-radius:0}.notice{background:white}h2,h3{break-after:avoid}footer{border-top:1px solid #888}}
''' + ''.join(presentation_style) + '''
</style></head><body><header><p>Household offline plan</p><h1>''' + escape(plan["title"]) + '''</h1><p>Region: ''' + escape(plan["region"]) + '''
Household review date: ''' + escape(plan["reviewed_on"]) + '''</p></header>
<p class="notice">This file may contain private information. View it only on a trusted local device and keep local copies and printouts secure.
Use the browser Print menu; all content is included in this file.</p>
<main><section><h2>Contacts</h2>''' + contacts + '''</section>
<section><h2>Agreed meeting points</h2>''' + meetings + '''</section>
<section><h2>Household and support needs</h2>''' + (household or '<p>Not provided</p>') + '''</section>
<section><h2>Household notes</h2><p>''' + escape(plan.get("notes", "Not provided")) + '''</p></section>
<section><h2>Sources entered by the author</h2><p>The tool does not fetch or verify sources; dates are supplied by the author. URLs are plain text.</p>''' + (sources or '<p>None supplied; regional requirements are unverified.</p>') + '''</section></main>
<footer><p>This tool organizes household decisions; it provides no medical advice and does not certify disaster safety. Follow local official instructions.</p>
<p>Open Resilience Lab · Schema version 1 · No scripts, telemetry, or external resources</p></footer>
</body></html>
'''


def _save_private_file(document, output_path, protected_paths=(), force=False, replace_template=False):
    """Write restrictive files; default exclusive creation, explicit atomic replacement."""
    output = Path(output_path)
    try:
        for protected in protected_paths:
            source = Path(protected)
            if output.resolve() == source.resolve() or (output.exists() and os.path.samefile(output, source)):
                raise PlanError("Output must not overwrite the input file.")
        if output.is_symlink() or (output.exists() and not output.is_file()):
            raise PlanError("Output must be a regular file, not a link or directory.")
        if force and replace_template and output.exists():
            # Even --force must never reset a filled household plan or source file.
            if output.stat().st_nlink != 1 or output.stat().st_size > MAX_INPUT_BYTES:
                raise PlanError("Only an unchanged template can be replaced. Choose a new template file.")
            with output.open("rb") as stream:
                existing = stream.read(MAX_INPUT_BYTES + 1)
            if existing != document.encode("utf-8"):
                raise PlanError("Only an unchanged template can be replaced. Choose a new template file.")
        output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not force:
            fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                    stream.write(document)
            except BaseException:
                output.unlink(missing_ok=True)
                raise
        else:
            fd, temporary = tempfile.mkstemp(prefix=".plan-", dir=output.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                    stream.write(document)
                os.replace(temporary, output)
            finally:
                Path(temporary).unlink(missing_ok=True)
    except FileExistsError:
        raise PlanError("Output already exists. Choose a new file or explicitly use --force.") from None
    except PlanError:
        raise
    except (OSError, ValueError, RuntimeError):
        raise PlanError("Unable to save the output file. Check local permissions and storage.") from None


def save_plan(document, output_path, input_path, force=False):
    _save_private_file(document, output_path, (input_path,), force=force)


def save_template(output_path=TEMPLATE_PATH, force=False):
    """Keep drafts under the local private-input directory and reject linked paths."""
    try:
        base = Path.cwd().resolve()
        root = base / "private-input"
        supplied = Path(output_path)
        output = supplied if supplied.is_absolute() else base / supplied
        if ".." in output.parts:
            raise PlanError("Template destination must be a JSON file inside private-input without parent traversal.")
        try:
            relative = output.relative_to(root)
        except ValueError:
            raise PlanError("Template destination must be a JSON file inside private-input.") from None
        if not relative.parts or output.suffix.lower() != ".json":
            raise PlanError("Template destination must be a JSON file inside private-input.")
        current = root
        for component in (None, *relative.parts):
            if component is not None:
                current = current / component
            if current.is_symlink():
                raise PlanError("Template destination and its directories must not be symbolic links.")
        # Create each new private directory with restrictive permissions, including
        # intermediate directories (Path.mkdir(parents=True) would use defaults).
        current = root
        for component in (None, *relative.parts[:-1]):
            if component is not None:
                current = current / component
            current.mkdir(mode=0o700, exist_ok=True)
        _save_private_file(template_document(), output, force=force, replace_template=True)
    except PlanError:
        raise
    except (OSError, ValueError, RuntimeError):
        raise PlanError("Unable to save the template. Check local permissions and storage.") from None


def _print_summary(plan):
    print("SUMMARY: " + json.dumps({
        "contacts": len(plan["contacts"]), "meeting_points": len(plan["meeting_points"]),
        "household_members": len(plan.get("household", [])), "sources": len(plan.get("sources", [])),
    }))


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    initializing = bool(arguments) and arguments[0] in ("init", "template")
    parser = PrivateArgumentParser(
        description=("Create a private editable JSON draft. Review it before generating a plan." if initializing else
                     "Generate an offline plan locally. Input and HTML contain private data; never commit real plans."),
        epilog=("Example: python3 resilience_plan.py init --output private-input/household.json" if initializing else
                "Start a new draft: python3 resilience_plan.py init (alias: template). Use init --help for details."))
    parser.add_argument("--schema-version", action="version", version="Schema version 1", help="print the supported input schema and exit")
    parser.add_argument("--quiet", action="store_true", help="suppress routine success messages; errors remain visible")
    if initializing:
        parser.add_argument("--output", default=TEMPLATE_PATH, help="JSON destination within private-input (default: private-input/household.json)")
        parser.add_argument("--force", action="store_true", help="replace only an unchanged template; filled plans and unrelated files remain protected")
    else:
        parser.add_argument("input", help="local UTF-8 JSON plan (prefix ./ for a file named init or template)")
        parser.add_argument("--output", help="local HTML destination (default: private-output/emergency-plan.html)")
        parser.add_argument("--force", action="store_true", help="explicitly replace an existing HTML output; never the input")
        parser.add_argument("--check", action="store_true", help="validate input without rendering or saving HTML; cannot be combined with --output or --force")
        parser.add_argument("--summary", action="store_true", help="print aggregate counts after success, without plan text or paths")
        parser.add_argument("--compact", action="store_true", help="reduce card and section spacing")
        parser.add_argument("--large-text", action="store_true", help="use larger screen and print text")
    try:
        args = parser.parse_args(arguments[1:] if initializing else arguments)
        if initializing:
            save_template(args.output, args.force)
            if not args.quiet:
                print("Template saved locally. Replace every placeholder and enter reviewed_on only after household review. "
                      "The YYYY-MM-DD placeholder intentionally fails date validation. Keep the template private.")
            return 0
        if args.check and (args.output is not None or args.force):
            raise PlanError("The --check option cannot be combined with --output or --force.")
        presentation = {"large_text": args.large_text, "compact": args.compact}
        if args.check and any(presentation.values()):
            raise PlanError("HTML presentation options cannot be combined with --check.")
        plan = load_plan(args.input)
        if args.check:
            if not args.quiet:
                print("Plan input passed format validation. No HTML was rendered or saved.")
            if args.summary:
                _print_summary(plan)
            return 0
        output = "private-output/emergency-plan.html" if args.output is None else args.output
        save_plan(render_plan(plan, **presentation), output, args.input, args.force)
    except PlanError as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 2
    if not args.quiet:
        print("Plan saved locally. Keep the input, HTML, and printouts private.")
    if args.summary:
        _print_summary(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
