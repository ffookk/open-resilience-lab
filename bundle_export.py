"""Local bundle rendering, transactional private saving, and bounded verification."""
import hashlib
import html
import json
import os
import re

from private_storage import (StorageError, open_directory_no_links, private_parent,
                             publish_private_bytes, read_regular_bytes, require_absent,
                             write_private_bytes)

PAYLOAD_NAMES = ("plan.html", "plan.txt", "cards.html")
BUNDLE_NAMES = frozenset((*PAYLOAD_NAMES, "manifest.json"))
MAX_BUNDLE_FILE_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _presentation(options):
    allowed = {"large_text", "compact", "high_contrast", "landscape", "neutral_title", "paper", "font"}
    if set(options) - allowed:
        raise StorageError("Unsupported bundle presentation option.")
    for name, value in options.items():
        if name not in {"paper", "font"} and type(value) is not bool:
            raise StorageError("Bundle display switches must be boolean.")
    if options.get("paper") not in (None, "a4", "letter") or options.get("font") not in (None, "sans", "serif", "monospace"):
        raise StorageError("Unsupported bundle paper or font setting.")
    return options


def render_text(plan):
    """Portable UTF-8 content; callers validate the plan before rendering."""
    lines = [plan["title"], "Region: " + plan["region"], "Household review date: " + plan["reviewed_on"],
             "", "PRIVATE HOUSEHOLD PLAN", "Keep this file and any printout private.", "", "CONTACTS"]
    for item in plan["contacts"]:
        lines.extend([item["name"], "Role: " + item["role"], "Contact: " + item["contact"], ""])
    lines.append("AGREED MEETING POINTS")
    for item in plan["meeting_points"]:
        lines.extend([item["label"], item["instructions"], ""])
    lines.append("HOUSEHOLD AND SUPPORT NEEDS")
    for item in plan.get("household", []):
        lines.extend([item["name"], item.get("needs", "Not provided"), ""])
    if not plan.get("household"):
        lines.append("Not provided")
    lines.extend(["", "HOUSEHOLD NOTES", plan.get("notes", "Not provided"), "", "SOURCES ENTERED BY THE AUTHOR",
                  "Source URLs and dates are user supplied. The tool does not fetch or verify them."])
    for item in plan.get("sources", []):
        lines.extend([item["title"], item["url"], "Entered review date: " + item["verified_on"], ""])
    if not plan.get("sources"):
        lines.append("None supplied; regional requirements are unverified.")
    lines.extend(["", "This file organizes household decisions. It provides no medical advice or disaster safety certification."])
    return "\n".join(lines) + "\n"


def render_cards(plan, options):
    """Expandable cut-out cards; no fixed height that could clip long instructions."""
    escape = lambda text: html.escape(text, quote=True)
    records = [("Contact", item["name"], "Role: " + item["role"] + "\nContact: " + item["contact"]) for item in plan["contacts"]]
    records.extend(("Meeting arrangement", item["label"], item["instructions"]) for item in plan["meeting_points"])
    cards = "".join('<article><p class="kind">' + kind + '</p><h2 dir="auto">' + escape(title)
                    + '</h2><p dir="auto">' + escape(body) + '</p><footer>' + escape(plan["title"])
                    + ' · Household review date: ' + escape(plan["reviewed_on"]) + '</footer></article>'
                    for kind, title, body in records)
    fonts = {None: "system-ui,sans-serif", "sans": "system-ui,sans-serif", "serif": "Georgia,serif", "monospace": "ui-monospace,monospace"}
    extra = "body{font-family:" + fonts[options.get("font")] + "}"
    if options.get("large_text"):
        extra += "body{font-size:18px}@media print{body{font-size:14pt}}"
    if options.get("high_contrast"):
        extra += "body{color:#000}article{border-color:#000}"
    size = (options.get("paper") or "") + (" landscape" if options.get("landscape") else "")
    if size.strip():
        extra += "@media print{@page{size:" + size.strip() + "}}"
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer"><title>Private contact and meeting cards</title>
<style>
*{box-sizing:border-box}body{margin:20px;color:#182b36;background:#fff;font:14px/1.4 system-ui,sans-serif;max-width:1000px}
h1{font-size:1.5em}h2{font-size:1.15em;margin:4px 0}p{white-space:pre-wrap;margin:6px 0}p,h1,h2,footer{overflow-wrap:anywhere}
main{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}article{border:1px dashed #59747a;padding:12px;break-inside:avoid;min-width:0}
article h2,article footer{white-space:pre-wrap}
.kind{font-weight:bold;text-transform:uppercase;font-size:.85em}footer{border-top:1px solid #bbb;margin-top:10px;padding-top:6px;font-size:.8em}
@media(max-width:600px){main{grid-template-columns:1fr}body{margin:12px}}
@media print{@page{margin:10mm}body{margin:0;max-width:none;font-size:10pt}header{font-size:9pt}main{gap:5mm}article{padding:4mm}h2{break-after:avoid}p{orphans:2;widows:2}}
''' + extra + '''</style></head><body><header><h1>Private contact and meeting cards</h1>
<p>Contacts and meeting arrangements only; consult the full plan for other information. Keep every cut-out card private.
Cards expand for long text. Preview pagination before printing or cutting.</p></header><main aria-label="Printable cards">''' + cards + '''</main></body></html>
'''


def create_bundle(plan, destination, *, html_renderer, presentation=None):
    """Publish manifest last; remove only this transaction's files on failure."""
    options = _presentation({} if presentation is None else dict(presentation))
    payloads = {"plan.html": html_renderer(plan, **options).encode("utf-8"),
                "plan.txt": render_text(plan).encode("utf-8"),
                "cards.html": render_cards(plan, options).encode("utf-8")}
    if any(len(payload) > MAX_BUNDLE_FILE_BYTES for payload in payloads.values()):
        raise StorageError("A generated bundle file exceeds the supported size limit.")
    manifest = {"bundle_format": 1, "schema_version": 1, "files": {
        name: {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)} for name, payload in payloads.items()}}
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    create_private_artifact_directory(payloads, manifest_bytes, destination)
    return manifest


def create_private_artifact_directory(payloads, manifest_bytes, destination):
    """Write trusted generated files in a new private directory, manifest last.

    Bundle and comparison exports share the same no-follow/no-clobber
    transaction. The manifest is the completion marker, not a signature.
    """
    if (not payloads or "manifest.json" in payloads
            or any(not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9.-]{0,63}", name)
                   or not isinstance(payload, bytes) or len(payload) > MAX_BUNDLE_FILE_BYTES
                   for name, payload in payloads.items())
            or not isinstance(manifest_bytes, bytes) or len(manifest_bytes) > MAX_MANIFEST_BYTES):
        raise StorageError("The generated private export has unsupported files or exceeds its size limit.")
    try:
        with private_parent(destination, "private-output", create=True) as (parent, leaf):
            require_absent(parent, leaf)
            os.mkdir(leaf, mode=0o700, dir_fd=parent)
            descriptor = None
            owned = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
            created = {}
            def remember(name, metadata):
                created[name] = (metadata.st_dev, metadata.st_ino)
            complete = False
            try:
                descriptor = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != (owned.st_dev, owned.st_ino):
                    raise StorageError("The new bundle directory changed during creation.")
                for name in payloads:
                    write_private_bytes(descriptor, name, payloads[name], on_create=remember)
                publish_private_bytes(descriptor, "manifest.json", manifest_bytes, on_create=remember)
                complete = True
            finally:
                if not complete and descriptor is not None:
                    for name, (device, inode) in created.items():
                        try:
                            current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                            if (current.st_dev, current.st_ino) == (device, inode):
                                os.unlink(name, dir_fd=descriptor)
                        except OSError:
                            pass
                if descriptor is not None:
                    os.close(descriptor)
                if not complete:
                    try:
                        current = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
                        if (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                            os.rmdir(leaf, dir_fd=parent)
                    except OSError:
                        pass
    except StorageError:
        raise
    except (OSError, ValueError, RuntimeError):
        raise StorageError("Private export creation failed. Check for incomplete output locally; existing destinations were not overwritten.") from None


def _manifest_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise StorageError("The bundle manifest contains duplicate fields.")
        result[key] = value
    return result


def _validate_manifest(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {"bundle_format", "schema_version", "files"}:
        raise StorageError("The bundle manifest structure is invalid.")
    if type(manifest["bundle_format"]) is not int or manifest["bundle_format"] != 1 or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise StorageError("The bundle format or plan schema is unsupported.")
    files = manifest["files"]
    if not isinstance(files, dict) or set(files) != set(PAYLOAD_NAMES):
        raise StorageError("The manifest must describe exactly the fixed bundle payload files.")
    for name in PAYLOAD_NAMES:
        record = files[name]
        if not isinstance(record, dict) or set(record) != {"sha256", "bytes"}:
            raise StorageError("A manifest file record is invalid.")
        if not isinstance(record["sha256"], str) or not DIGEST.fullmatch(record["sha256"]):
            raise StorageError("A manifest digest is invalid.")
        if type(record["bytes"]) is not int or not 0 <= record["bytes"] <= MAX_BUNDLE_FILE_BYTES:
            raise StorageError("A manifest byte count is invalid.")
    return files


def verify_bundle(directory):
    """Check fixed names and bounded bytes, never paths supplied by a manifest."""
    try:
        with open_directory_no_links(directory) as descriptor:
            if set(os.listdir(descriptor)) != BUNDLE_NAMES:
                raise StorageError("The bundle is incomplete or contains unexpected files.")
            raw = read_regular_bytes(descriptor, "manifest.json", MAX_MANIFEST_BYTES)
            manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=_manifest_object)
            expected = _validate_manifest(manifest)
            for name in PAYLOAD_NAMES:
                payload = read_regular_bytes(descriptor, name, MAX_BUNDLE_FILE_BYTES)
                if len(payload) != expected[name]["bytes"] or hashlib.sha256(payload).hexdigest() != expected[name]["sha256"]:
                    raise StorageError("Bundle content does not match the integrity manifest.")
            if set(os.listdir(descriptor)) != BUNDLE_NAMES:
                raise StorageError("Bundle entries changed during verification.")
    except StorageError:
        raise
    except (OSError, ValueError, RecursionError, RuntimeError):
        raise StorageError("Unable to verify this bundle safely. Inspect its format and file types locally.") from None
    return True
