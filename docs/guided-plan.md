# Guided local plan creation

The wizard creates a complete schema-version-1 JSON plan without requiring manual JSON editing:

```sh
python3 resilience_plan.py wizard --output private-input/household.json
python3 resilience_plan.py private-input/household.json --check
python3 resilience_plan.py private-input/household.json
```

Run it from the repository root in a trusted local terminal. Every answer is hidden as you type and is not repeated in output. This protects terminal output from routine disclosure; it does not protect against a compromised device, terminal recording, clipboard tools, or access to the resulting files. Hidden prompts are mandatory: piped input and an echoing terminal fallback are refused.

The wizard asks for a title, region, actual household review date, 1–20 contacts, and 1–10 meeting arrangements. It also supports up to 20 optional household members, optional notes, and up to 20 sources. Enter only information your household has already agreed; the tool supplies no emergency, medical, or regional policy advice. Answers are entered one line at a time. Use a trusted local editor after saving if you need multiline text.

Invalid dates, empty required fields, unsupported characters, excessive lengths, out-of-range counts, and invalid source URLs are retried with a fixed explanation. Optional text can be skipped with Enter, and optional lists can use a count of `0`. The existing full-plan validator checks the completed result before saving. Source URLs are never fetched.

At the beginning and end, answer `yes` or `no` to fixed confirmation prompts. These confirmations and the entered review dates are your statements, not independent review or certification. The terminal does not display the completed plan; inspect the resulting file privately if needed.

Type `/cancel` at any prompt, press Ctrl-C, or end input to cancel before saving. Cancellation or EOF while answering leaves no file or directory. The command returns `130` for cancellation, `2` for an input/storage problem, and `0` after saving a validated plan.

The output must be a new `.json` file under the current directory's `private-input/`. Existing files, links, parent traversal, and destinations outside that directory are refused; there is no overwrite option. Newly created managed directories use mode `0700` and the file uses `0600`. Existing managed directories must already be owned by the current user and have no group/other access. Their permissions are not silently changed.

This new managed-write workflow requires POSIX directory-handle and no-follow operations, as provided by supported macOS and Linux implementations. It fails safely where these operations are unavailable. Existing generation and template commands keep their previous behavior.

The JSON is written completely before it is published under the requested filename. Handled write failures remove the pending file; an interruption after publication can leave a complete plan. Check the destination privately after an interruption. Abrupt process or machine failure can leave a private temporary file; never publish it or assume it is a reviewed plan. Keep all personal JSON, HTML, PDFs, and printouts private. Git ignore rules are not encryption or access control.

For deterministic development tests, `collect_plan(read_answer=..., report=...)` accepts a supplied reader and reporter; `run_wizard(destination, read_answer=..., report=...)` additionally saves the result. Use synthetic answers only. The reporter receives fixed guidance without answers; a reader signals cancellation with EOF, KeyboardInterrupt, or `/cancel`.
