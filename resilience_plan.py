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
            address.port  # Reject malformed or out-of-range ports without requesting the URL.
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


def render_plan(plan, *, large_text=False, compact=False, high_contrast=False, omit_notes=False, landscape=False, neutral_title=False, omit_household=False, omit_region=False, paper=None, font=None):
    validate_plan(plan)
    presentation_style = []
    if landscape:
        presentation_style.append('@media print{@page{size:landscape}}')
    if high_contrast:
        presentation_style.append('body{color:#000;background:#fff}article,.notice{background:#fff;border-color:#000}h2{border-color:#000}')
    if compact:
        presentation_style.append('article{padding:8px;margin:6px 0}h2{margin-top:18px}body{line-height:1.4}')
    if large_text:
        presentation_style.append('body{font-size:20px}@media print{body{font-size:14pt}}')
    escape = lambda value: html.escape(value, quote=True)
    cards = lambda entries: "".join(
        '<article><h3 dir="auto">' + escape(title) + '</h3><p dir="auto">' + escape(body) + '</p></article>'
        for title, body in entries
    )
    contacts = cards((item["name"] + " · " + item["role"], item["contact"]) for item in plan["contacts"])
    meetings = cards((item["label"], item["instructions"]) for item in plan["meeting_points"])
    household = cards((item["name"], item.get("needs", "Not provided")) for item in plan.get("household", []))
    sources = cards((item["title"], item["url"] + "\nEntered review date: " + item["verified_on"])
                    for item in plan.get("sources", []))
    fonts = {"sans": "system-ui,sans-serif", "serif": "Georgia,serif", "monospace": "ui-monospace,monospace"}
    if isinstance(font, str) and font in fonts:
        presentation_style.append("body{font-family:" + fonts[font] + "}")
    if paper in ("a4", "letter"):
        presentation_style.append("@media print{@page{size:" + paper + (" landscape" if landscape else "") + "}}")
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer">
<title>''' + ("Household offline plan" if neutral_title else escape(plan["title"])) + '''</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:32px;color:#182b36;background:#f5f7f8;line-height:1.6}
h1{line-height:1.25;overflow-wrap:anywhere}h2,h3{overflow-wrap:anywhere}h2{margin-top:30px;border-bottom:2px solid #59747a;padding-bottom:5px}h3{margin:0 0 6px}article{background:white;border:1px solid #cbd5d9;border-radius:8px;padding:16px;margin:12px 0;break-inside:avoid}
p{white-space:pre-wrap;overflow-wrap:anywhere;margin:0 0 8px}.notice{border-left:4px solid #59747a;padding:12px;background:#e7eff1}footer{font-size:.9rem;margin-top:32px}
.skip-link{position:absolute;left:8px;top:-100px;background:#fff;color:#182b36;padding:8px}.skip-link:focus{top:8px}@media print{.skip-link{display:none}}
nav{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}nav a{color:inherit;padding:10px 12px;min-height:44px;display:inline-flex;align-items:center}@media print{nav{display:none}}
.screen-only a{color:inherit}@media print{.screen-only{display:none}}
:focus-visible{outline:3px solid currentColor;outline-offset:4px}
section:target{outline:2px solid currentColor;outline-offset:6px}section{scroll-margin-top:16px}
@media screen and (prefers-color-scheme:dark){body{color:#edf3f5;background:#16242b}article{background:#20333d;border-color:#829aa6}.notice{background:#263e49}.skip-link{color:#edf3f5;background:#16242b}}
@media (forced-colors:active){body,article,.notice,.skip-link{color:CanvasText;background:Canvas}article,.notice,h2{border-color:CanvasText}a{color:LinkText}}
@media print{p{orphans:3;widows:3}}
.source-list article p{font-family:ui-monospace,monospace;overflow-wrap:anywhere;font-size:.95em}
@media screen and (min-width:1000px){#contacts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}#contacts>h2{grid-column:1/-1}#contacts>article{margin:0}}
@media(max-width:600px){body{padding:16px}h1{font-size:1.7rem}}
@media print{@page{margin:15mm}body{background:white;padding:0;max-width:none;font-size:11pt}article{border-radius:0}.notice{background:white}h2,h3{break-after:avoid;page-break-after:avoid}article p{break-before:avoid-page}footer{border-top:1px solid #888}}
''' + ''.join(presentation_style) + '''
</style></head><body><a class="skip-link" href="#plan-content">Skip to plan content</a><header id="plan-top"><p>Household offline plan</p><h1 id="plan-title">''' + escape(plan["title"]) + '''</h1><p>''' + ('' if omit_region else "Region: " + escape(plan["region"]) + "\n") + '''Household review date: <time datetime="''' + escape(plan["reviewed_on"]) + '''">''' + escape(plan["reviewed_on"]) + '''</time></p></header>
<p class="notice">This file may contain private information. View it only on a trusted local device and keep local copies and printouts secure.
Use the browser Print menu; all content is included in this file.</p>
<nav aria-label="Plan sections"><a href="#contacts">Contacts</a> <a href="#meeting-points">Meeting points</a> ''' + ('' if omit_household else '<a href="#household">Household</a> ') + ('' if omit_notes else '<a href="#notes">Notes</a> ') + '''<a href="#sources">Sources</a></nav>
<main id="plan-content" tabindex="-1" aria-labelledby="plan-title"><section id="contacts" aria-labelledby="contacts-title"><h2 id="contacts-title">Contacts</h2>''' + contacts + '''</section>
<section id="meeting-points" aria-labelledby="meetings-title"><h2 id="meetings-title">Agreed meeting points</h2>''' + meetings + '''</section>
''' + ('' if omit_household else '<section id="household"><h2>Household and support needs</h2>' + (household or '<p>Not provided</p>') + '</section>') + '''
''' + ('' if omit_notes else '<section id="notes"><h2>Household notes</h2><p>' + escape(plan.get("notes", "Not provided")) + '</p></section>') + '''
<section id="sources" class="source-list"><h2>Sources entered by the author</h2><p>The tool does not fetch or verify sources; dates are supplied by the author. URLs are plain text.</p>''' + (sources or '<p>None supplied; regional requirements are unverified.</p>') + '''</section></main>
<footer><p class="screen-only"><a href="#plan-top">Back to top</a></p><p>This tool organizes household decisions; it provides no medical advice and does not certify disaster safety. Follow local official instructions.</p>
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


class WizardCancelled(Exception):
    """The user stopped before any plan was published."""


def _read_private_answer(prompt):
    """Refuse getpass's echoing fallback instead of exposing a private answer."""
    import getpass
    import warnings
    try:
        trusted = sys.stdin is not None and sys.stderr is not None and sys.stdin.isatty() and sys.stderr.isatty()
    except (OSError, ValueError):
        trusted = False
    if not trusted:
        raise PlanError("The wizard requires a trusted interactive terminal with hidden input.") from None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt, stream=sys.stderr)
    except (getpass.GetPassWarning, OSError, ValueError):
        raise PlanError("Hidden terminal input is unavailable. No plan was saved.") from None


def collect_plan(read_answer=None, report=None):
    """Collect synthetic or local private answers; injectable hooks support tests.

    The reader receives fixed prompts and returns strings. The reporter only
    receives fixed guidance, never answers. EOF and interruptions cancel.
    """
    read_answer = _read_private_answer if read_answer is None else read_answer
    report = (lambda message: print(message, file=sys.stderr)) if report is None else report

    def ask(prompt, check, *, optional=False):
        while True:
            try:
                answer = read_answer(prompt)
            except (EOFError, KeyboardInterrupt):
                raise WizardCancelled from None
            if not isinstance(answer, str):
                raise PlanError("The interactive reader did not return text.")
            if answer == "/cancel":
                raise WizardCancelled
            if optional and answer == "":
                return None
            try:
                check(answer)
            except PlanError as error:
                report(str(error))
                continue
            return answer

    def count(prompt, minimum, maximum):
        def validate(value):
            if len(value) > 2 or not value.isascii() or not value.isdecimal() or not minimum <= int(value) <= maximum:
                raise PlanError("Enter a whole-number count within the range shown in the prompt.")
        return int(ask(prompt, validate))

    def yes(prompt):
        def validate(value):
            if value.lower() not in ("yes", "no"):
                raise PlanError("Enter yes or no.")
        return ask(prompt, validate).lower() == "yes"

    report("Answers are hidden and are not repeated. Use a trusted local terminal. Type /cancel or press Ctrl-C to stop.")
    report("Enter only necessary information already agreed by your household. This tool does not provide or verify emergency advice.")
    if not yes("Have you reviewed the household arrangements and chosen a trusted local destination? (yes/no): "):
        raise WizardCancelled
    plan = {"schema_version": 1,
            "title": ask("Plan title (up to 120 characters): ", lambda value: _text(value, 120)),
            "region": ask("Applicable region (up to 120 characters): ", lambda value: _text(value, 120)),
            "reviewed_on": ask("Actual household review date (YYYY-MM-DD): ", _date),
            "contacts": [], "meeting_points": [], "household": [], "sources": []}
    for _ in range(count("Number of contacts (1-20): ", 1, 20)):
        report("Enter the next contact.")
        plan["contacts"].append({"name": ask("Contact name: ", lambda value: _text(value, 200)),
                                 "role": ask("Agreed contact role: ", lambda value: _text(value, 200)),
                                 "contact": ask("Contact details: ", lambda value: _text(value, 200))})
    for _ in range(count("Number of meeting arrangements (1-10): ", 1, 10)):
        report("Enter the next meeting arrangement.")
        plan["meeting_points"].append({"label": ask("Meeting arrangement label: ", lambda value: _text(value, 120)),
                                       "instructions": ask("Agreed meeting instructions: ", lambda value: _text(value, 2000))})
    for _ in range(count("Number of optional household member entries (0-20): ", 0, 20)):
        report("Enter the next optional household member.")
        member = {"name": ask("Member name: ", lambda value: _text(value, 120))}
        needs = ask("Necessary support needs, or Enter to omit: ", lambda value: _text(value, 1000), optional=True)
        if needs is not None:
            member["needs"] = needs
        plan["household"].append(member)
    notes = ask("Optional notes, or Enter to omit: ", lambda value: _text(value, 4000), optional=True)
    if notes is not None:
        plan["notes"] = notes
    for _ in range(count("Number of optional source entries (0-20): ", 0, 20)):
        report("Enter the next source. Sources and review dates remain your own statements.")
        title = ask("Source title: ", lambda value: _text(value, 200))
        def source_url(value):
            candidate = dict(plan, sources=[{"title": title, "url": value, "verified_on": "2000-01-01"}])
            validate_plan(candidate)
        url = ask("HTTPS source URL without credentials, query, or fragment: ", source_url)
        reviewed = ask("Actual source review date (YYYY-MM-DD): ", _date)
        plan["sources"].append({"title": title, "url": url, "verified_on": reviewed})
    validate_plan(plan)
    if len(json.dumps(plan, ensure_ascii=False, indent=2).encode("utf-8")) + 1 > MAX_INPUT_BYTES:
        raise PlanError("The completed plan exceeds the input size limit. No plan was saved.")
    if not yes("Save this reviewed local plan without displaying its contents? (yes/no): "):
        raise WizardCancelled
    return plan


def run_wizard(destination, *, read_answer=None, report=None):
    from private_storage import StorageError, check_private_destination, save_private_json
    try:
        check_private_destination(destination, "private-input", ".json")
        plan = collect_plan(read_answer, report)
        save_private_json(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", destination)
    except StorageError as error:
        raise PlanError(str(error)) from None
    return plan


def _wizard_command(arguments):
    parser = PrivateArgumentParser(prog="resilience-plan wizard", allow_abbrev=False,
                                   description="Create a reviewed local plan with hidden terminal prompts. No network or automatic fact verification.")
    parser.add_argument("--output", required=True, help="new JSON destination under private-input")
    try:
        args = parser.parse_args(arguments)
        run_wizard(args.output)
    except WizardCancelled:
        print("Plan creation cancelled before saving. No plan was saved.", file=sys.stderr)
        return 130
    except KeyboardInterrupt:
        print("Plan creation interrupted. Check the destination locally; any published plan is complete.", file=sys.stderr)
        return 130
    except PlanError as error:
        print("Error: " + str(error), file=sys.stderr)
        return 2
    print("Validated plan saved privately. Format validation and your confirmation are not independent verification.")
    return 0


def export_bundle(input_path, destination, *, presentation=None):
    from bundle_export import create_bundle
    from private_storage import StorageError
    plan = load_plan(input_path)
    try:
        return create_bundle(plan, destination, html_renderer=render_plan, presentation=presentation)
    except StorageError as error:
        raise PlanError(str(error)) from None


def _bundle_command(arguments, *, verify=False):
    from bundle_export import verify_bundle
    from private_storage import StorageError
    parser = PrivateArgumentParser(prog="resilience-plan " + ("verify-bundle" if verify else "bundle"), allow_abbrev=False,
                                   description="Inspect or create private offline exports. No upload, encryption, or automatic redaction.")
    if verify:
        parser.add_argument("directory", help="local directory containing the four fixed bundle files")
    else:
        parser.add_argument("input", help="local validated JSON plan")
        parser.add_argument("--output", required=True, help="new directory under private-output")
        parser.add_argument("--paper", choices=("a4", "letter"), help="request a print paper size")
        parser.add_argument("--font", choices=("sans", "serif", "monospace"), help="choose a local font family")
        for flag in ("large-text", "compact", "high-contrast", "landscape", "neutral-title"):
            parser.add_argument("--" + flag, action="store_true", help="apply this existing presentation option to HTML output")
    try:
        args = parser.parse_args(arguments)
        if verify:
            verify_bundle(args.directory)
        else:
            options = {key: getattr(args, key) for key in ("large_text", "compact", "high_contrast", "landscape", "neutral_title", "paper", "font")}
            export_bundle(args.input, args.output, presentation=options)
    except KeyboardInterrupt:
        print("Bundle operation interrupted. Verify any remaining private bundle before use.", file=sys.stderr)
        return 130
    except (PlanError, StorageError) as error:
        print("Error: " + str(error), file=sys.stderr)
        return 2
    print("Bundle integrity verified for all expected files; plan facts remain unverified." if verify else
          "Private bundle created. Keep every file and printout private; this is not an upload or redaction workflow.")
    return 0


def _print_summary(plan):
    print("SUMMARY: " + json.dumps({
        "contacts": len(plan["contacts"]), "meeting_points": len(plan["meeting_points"]),
        "household_members": len(plan.get("household", [])), "sources": len(plan.get("sources", [])),
    }))


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "wizard":
        return _wizard_command(arguments[1:])
    if arguments and arguments[0] in ("bundle", "verify-bundle"):
        return _bundle_command(arguments[1:], verify=arguments[0] == "verify-bundle")
    initializing = bool(arguments) and arguments[0] in ("init", "template")
    parser = PrivateArgumentParser(
        allow_abbrev=False,
        description=("Create a private editable JSON draft. Review it before generating a plan." if initializing else
                     "Generate an offline plan locally. Input and HTML contain private data; never commit real plans."),
        epilog=("Example: python3 resilience_plan.py init --output private-input/household.json" if initializing else
                "Create a plan: python3 resilience_plan.py wizard --output private-input/household.json. Or start a draft with init (alias: template). Use bundle --help or verify-bundle --help for offline exports."))
    parser.add_argument("--schema-version", action="version", version="Schema version 1", help="print the supported input schema and exit")
    parser.add_argument("--quiet", action="store_true", help="suppress routine success messages; errors remain visible")
    if initializing:
        parser.add_argument("--output", default=TEMPLATE_PATH, help="JSON destination within private-input (default: private-input/household.json)")
        parser.add_argument("--force", action="store_true", help="replace only an unchanged template; filled plans and unrelated files remain protected")
    else:
        parser.add_argument("input", help="local UTF-8 JSON plan (prefix ./ if its name matches a command)")
        parser.add_argument("--output", help="local HTML destination (default: private-output/emergency-plan.html)")
        parser.add_argument("--force", action="store_true", help="explicitly replace an existing HTML output; never the input")
        parser.add_argument("--check", action="store_true", help="validate input without rendering or saving HTML; cannot be combined with --output or --force")
        parser.add_argument("--summary", action="store_true", help="print aggregate counts after success, without plan text or paths")
        parser.add_argument("--font", choices=("sans", "serif", "monospace"), help="choose a local system font family")
        parser.add_argument("--paper", choices=("a4", "letter"), help="request A4 or Letter paper; otherwise keep browser defaults")
        parser.add_argument("--omit-region", action="store_true", help="exclude the entered region from the HTML header")
        parser.add_argument("--omit-household", action="store_true", help="exclude the household and support-needs section from HTML")
        parser.add_argument("--neutral-title", action="store_true", help="use a fixed browser-tab title while retaining the visible plan heading")
        parser.add_argument("--landscape", action="store_true", help="request landscape print orientation")
        parser.add_argument("--omit-notes", action="store_true", help="exclude household notes from generated HTML")
        parser.add_argument("--high-contrast", action="store_true", help="use black text and borders on white")
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
        presentation = {"large_text": args.large_text, "compact": args.compact, "high_contrast": args.high_contrast, "omit_notes": args.omit_notes, "landscape": args.landscape, "neutral_title": args.neutral_title, "omit_household": args.omit_household, "omit_region": args.omit_region, "paper": args.paper, "font": args.font}
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
