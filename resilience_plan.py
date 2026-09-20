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


class PlanError(ValueError):
    """An intentionally data-free message that is safe to show in a terminal."""


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


def render_plan(plan):
    validate_plan(plan)
    escape = lambda value: html.escape(value, quote=True)
    cards = lambda entries: "".join(
        '<article><h3>' + escape(title) + '</h3><p>' + escape(body) + '</p></article>'
        for title, body in entries
    )
    contacts = cards((item["name"] + " · " + item["role"], item["contact"]) for item in plan["contacts"])
    meetings = cards((item["label"], item["instructions"]) for item in plan["meeting_points"])
    household = cards((item["name"], item.get("needs", "未填写 / Not provided")) for item in plan.get("household", []))
    sources = cards((item["title"], item["url"] + "\n填写的核对日期 / Entered review date: " + item["verified_on"])
                    for item in plan.get("sources", []))
    return '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
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
</style></head><body><header><p>家庭离线应急预案 / Household offline plan</p><h1>''' + escape(plan["title"]) + '''</h1><p>适用地区 / Region: ''' + escape(plan["region"]) + '''
家庭核对日期 / Household review date: ''' + escape(plan["reviewed_on"]) + '''</p></header>
<p class="notice">本文件可能包含私人资料。仅在受信任的本地设备查看；打印件也须妥善保管。
This file may contain private information. Keep local copies and printouts secure.
通过浏览器“打印”菜单打印；所有内容均已包含在本文件中。</p>
<main><section><h2>紧急联系人 / Contacts</h2>''' + contacts + '''</section>
<section><h2>约定集合安排 / Agreed meeting points</h2>''' + meetings + '''</section>
<section><h2>家庭成员与支持需求 / Household and support needs</h2>''' + (household or '<p>未填写 / Not provided</p>') + '''</section>
<section><h2>家庭备注 / Household notes</h2><p>''' + escape(plan.get("notes", "未填写 / Not provided")) + '''</p></section>
<section><h2>填写者提供的资料来源 / Sources entered by the author</h2><p>工具没有访问或核实这些资料；日期由填写者提供。链接仅按文本展示。
The tool does not fetch or verify sources; dates are supplied by the author. URLs are plain text.</p>''' + (sources or '<p>未填写；地区要求尚未由本工具核验。 / None supplied; regional requirements are unverified.</p>') + '''</section></main>
<footer><p>本工具只整理家庭自行约定的内容，不提供医疗建议，也不验证预案在具体灾害中的安全性。应急情况请依照当地官方指引。
This tool organizes household decisions; it provides no medical advice and does not certify disaster safety. Follow local official instructions.</p>
<p>Open Resilience Lab · 格式版本 / Schema version 1 · 无脚本、无遥测、无外部资源 / No scripts, telemetry, or external resources</p></footer>
</body></html>
'''


def save_plan(document, output_path, input_path, force=False):
    """Write restrictive files; default exclusive creation, explicit atomic replacement."""
    output = Path(output_path)
    source = Path(input_path)
    try:
        if output.resolve() == source.resolve() or (output.exists() and os.path.samefile(output, source)):
            raise PlanError("Output must not overwrite the input file.")
        if output.is_symlink() or (output.exists() and not output.is_file()):
            raise PlanError("Output must be a regular file, not a link or directory.")
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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate an offline plan locally. Input and HTML contain private data; never commit real plans.")
    parser.add_argument("input", help="local UTF-8 JSON plan")
    parser.add_argument("--output", default="private-output/emergency-plan.html", help="local HTML destination (default: private-output/emergency-plan.html)")
    parser.add_argument("--force", action="store_true", help="explicitly replace an existing HTML output; never the input")
    args = parser.parse_args(argv)
    try:
        plan = load_plan(args.input)
        save_plan(render_plan(plan), args.output, args.input, args.force)
    except PlanError as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 2
    print("Plan saved locally. Keep the input, HTML, and printouts private.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
