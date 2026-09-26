# Open Resilience Lab

Turn public safety strategies into verifiable questions and collaboratively develop tools for emergency preparedness, information verification, cyber defense, and continuity of essential services.

Each task should answer three questions: who faces what difficulty, what will be delivered, and how its usefulness will be demonstrated.
Swiss security policy strategy provides the first research leads. Independent contributors maintain this project; it is not government endorsed or commissioned.

## Current status

A Python CLI prototype with no third-party dependencies creates a blank offline graphical plan studio, creates a reviewed local plan through a guided terminal wizard, creates editable JSON drafts, generates self-contained HTML household plans, exports private offline bundles with printable cards and an integrity check, and compares saved revisions in private JSON and HTML reports.
The tool makes no network requests and runs no telemetry. Printable plan pages contain no scripts or external resources. The optional studio uses fixed local JavaScript for editing; it has no network requests, browser storage, or external assets. Source URLs appear only as text.
Input validation, HTML escaping, overwrite protection, file permissions, and generation with Python sockets disabled have been checked.
The current English fictional plan and cards have a bounded desktop/narrow-viewport and A4 PDF check record; selected editor, generated-page, and revision-review behavior is covered by Chromium/Firefox automation. See the [browser check record](docs/browser-check.md) for exact samples and limits.
Physical mobile devices, screen readers, physical printing, pagination beyond the recorded fictional samples, and real household trials remain unverified. Regional policy requirements have not been verified either.

## Run locally

Requires Python 3.10 or later. No `pip install` is needed, and generation works offline once the repository and Python are available.
Use `python3 resilience_plan.py --help` to inspect generator options.
Start with the entirely fictional example:

```sh
python3 resilience_plan.py examples/fictional-household.json
```

Open `private-output/emergency-plan.html` in a local browser and use its Print menu to print or save a PDF.
The output includes print styles, but pagination should still be previewed for each browser and for long content.
The program does not open a browser or echo household details or input paths in the terminal.
A successful command returns exit code `0`; input, argument, or save failures return `2`. Scripts should check the exit code before using the output.

To validate an input without rendering or saving HTML, add `--check`:

```sh
python3 resilience_plan.py examples/fictional-household.json --check
```

This mode uses the same input-format validation and prints a fixed result without input values or paths. It creates no output files or directories and returns `0` on success or `2` on failure.
`--check` cannot be combined with an explicit `--output` or `--force`, and is not accepted by `init` or `template`.
Passing format validation does not verify household arrangements, source facts, or emergency safety.

To edit a plan through a graphical form, generate the [offline household plan studio](docs/plan-studio.md):

```sh
python3 resilience_plan.py studio --output private-output/plan-studio.html
```

Open the resulting file locally in a modern browser. It starts blank with no household data, review date, or implied readiness. Add, remove, and reorder contacts, meeting arrangements, household entries, and sources; preview the draft; import a local schema-version-1 JSON file; and explicitly download validated JSON, printable full-plan HTML, or contact/meeting cards. Every field remains editable locally, including optional notes and support needs.

The studio keeps edits only in its tab. It has no autosave or browser storage. Check that a JSON download has actually been saved before selecting **I saved the JSON**; printable exports do not save editable JSON. Closing or refreshing can lose work, and a browser warning is not guaranteed. Input, downloads, previews, and printouts may contain private information. Browser download destinations and permissions are controlled by the browser, not the Python generator.

To create a complete plan interactively without editing JSON, use the [guided local wizard](docs/guided-plan.md):

```sh
python3 resilience_plan.py wizard --output private-input/household.json
```

The wizard uses hidden terminal prompts, retries invalid entries, and saves only after complete validation and your confirmation. Cancellation or EOF while answering leaves no output. It requires a trusted interactive terminal and POSIX private-storage support; confirmation is not independent review.

To export a validated plan as full HTML, portable text, and compact printable contact/meeting cards, create a new [private offline bundle](docs/private-bundles.md):

```sh
python3 resilience_plan.py bundle examples/fictional-household.json --output private-output/example-bundle
python3 resilience_plan.py verify-bundle private-output/example-bundle
```

Open `plan.html` or `cards.html` inside the new directory locally. The fourth file, `manifest.json`, records byte counts and SHA-256 digests; verification detects missing, changed, malformed, or unexpected files. It does not establish authorship, factual accuracy, or confidentiality. All bundle files and printouts may contain private data. This workflow performs no upload, encryption, or automatic redaction.

To review differences between two saved plans, create a [private revision review](docs/plan-revisions.md):

```sh
python3 resilience_plan.py compare private-input/before.json private-input/after.json --output private-output/revision-01
python3 resilience_plan.py verify-review private-input/before.json private-input/after.json private-output/revision-01
```

The new directory contains deterministic `comparison.json`, a self-contained `review.html`, and an integrity manifest. Reports show added, removed, and changed values, section counts, and canonical input fingerprints. Lists are compared by ordered position; names and duplicate entries are never guessed as identities. Reports retain removed private values. Neither input is changed, and no household review or source verification is performed. The verifier checks all three artifacts against both inputs without writing output. Existing destinations are never overwritten.

To prepare a personal plan manually, run `init` from the repository root to create a draft in the ignored `private-input/` directory:

```sh
python3 resilience_plan.py init
# Open private-input/household.json in a trusted local editor.
# Replace every placeholder and enter the actual reviewed_on date after household review.
python3 resilience_plan.py private-input/household.json
```

The initial `reviewed_on` value is `YYYY-MM-DD` and **intentionally fails date validation**. The tool does not insert today's date or claim that household review has taken place.
Enter the review date only after reviewing the plan. To try generation and printing, use the fictional example above.
The tool does not detect or verify the other placeholders. The person completing the draft must replace and check each one; passing format validation does not establish that the content has been reviewed.

`template` is an alias for `init`; `python3 resilience_plan.py init --help` displays template command help.
For JSON input files named `studio`, `wizard`, `bundle`, `verify-bundle`, `compare`, or `verify-review`, prefix the filename with `./`. For files named `init` or `template`, use
`python3 resilience_plan.py ./init` or `python3 resilience_plan.py ./template` to read it as an input file.
Use `--output private-input/another-plan.json` to create another draft. The destination must be under
`private-input/` in the current directory and have a `.json` extension; neither the destination nor its directories may be symbolic links.
Existing files are protected by default. `init --force` **can only recreate an entirely unchanged draft produced by the current version of this tool**. Filled plans,
other JSON files, hard links, and unrelated source files cannot be overwritten this way. Choose a new filename when you need a new draft.
On POSIX systems, the JSON file and each newly created template directory use permissions `0600` and `0700`, respectively.
Existing directory permissions are unchanged. Windows users should configure access through their operating system.

Existing HTML output is protected by default; add `--force` when you intend to replace it. Even with this option, the tool refuses to overwrite the input,
a hard link to the input, or any output symbolic link. Created HTML files use `0600` permissions on POSIX systems,
and a newly created immediate output directory uses `0700`; existing directory permissions are unchanged.

**Real input files, bundle files, HTML, PDFs, and printouts may contain private information.** Git ignores `private-input/` and `private-output/`,
but `.gitignore` provides neither encryption nor access control and cannot prevent forced commits, cloud synchronization, or editor extension access.
Use trusted local devices and storage, enter only necessary information, check backup and printing locations, and never paste a real plan into an issue or PR.
HTML is for previewing and printing. To update a plan, edit the original JSON and generate it again; importing HTML back into JSON is not supported.

## Input format and boundaries

See the complete [fictional household JSON](examples/fictional-household.json). All objects reject unknown fields, and text must not be empty.
The file must be UTF-8 JSON no larger than 256 KiB. Duplicate keys, invalid dates, and unsupported control characters are rejected.
See [usage notes](docs/usage-notes.md) for more input and command details.

| Field | Requirements |
|---|---|
| `schema_version` | Integer `1` |
| `title`, `region` | Required text, at most 120 characters each |
| `reviewed_on` | Date of the household's own review, in `YYYY-MM-DD` format |
| `contacts` | 1–20 entries; each requires `name`, `role`, and `contact`, at most 200 characters each |
| `meeting_points` | 1–10 entries; `label` at most 120 characters and `instructions` at most 2000 characters |
| `household` | Optional, at most 20 entries; required `name` at most 120 characters and optional `needs` at most 1000 characters |
| `notes` | Optional text, at most 4000 characters |
| `sources` | Optional, at most 20 entries; required `title` at most 200 characters, `url` at most 2000 characters, and a `verified_on` date |

Source URLs must use HTTPS and contain no credentials, query parameters, fragments, or whitespace. The tool does not visit these URLs or verify supplied dates or information.
This tool organizes arrangements agreed by a household. It provides neither specific medical advice nor disaster safety certification. The person completing the plan should check regional information against local official sources.

## Development checks

```sh
python3 -m unittest discover -s tests -v
```

Functional tests cover malicious HTML escaping, required fields and type/length limits, invalid/duplicate/oversized JSON, errors that do not echo input,
overwrite and link protection, POSIX permissions, absence of external resource markup, and template creation and CLI generation with Python sockets disabled.
Template tests also cover the unreviewed date placeholder, generation through the original CLI after editing, overwrite restrictions, parent-directory links, directory boundaries, and argument errors that do not echo supplied values.
Wizard tests cover hidden-input refusal, validated retries, cancellation, safe saving, and no-clobber behavior. Bundle tests cover complete exports, escaping, bounded integrity checks, malformed or linked files, private permissions, and cleanup after handled failures or interruptions.
Revision tests cover canonical fingerprints, ordered/duplicate list semantics, nested additions/removals, safe literal rendering, private no-clobber exports, tamper detection, and bounded CLI diagnostics including direct script execution.
Studio parity and state checks run through Node when it is available on `PATH`; unittest explicitly skips those checks when Node is absent. CI installs Node 24 in every Python matrix job so these checks run. A separate Chromium/Firefox suite exercises the Studio and generated pages; see the [browser check guide](docs/browser-check.md). A skipped test is not JavaScript parity evidence. Normal studio generation and use need only Python and a browser, without Node or package installation.
These checks do not establish the privacy or reliability of browser extensions, operating systems, cloud synchronization, printers, or real disaster use.
Before contributing, also follow the repository checks in the [privacy guide](docs/privacy.md).

## First project: an offline household plan

The goal is to help a household find previously agreed emergency contacts and meeting arrangements after losing network access.

Implemented workflow and remaining goals:

- Implemented: enter contacts, meeting arrangements, and optional support needs in local JSON and generate HTML without external resources.
- Implemented: English section labels, print styles, narrow-screen CSS, and an entirely fictional example. On 2026-09-22, the unchanged English example was checked in headless Chromium 153 at desktop/narrow viewports and as A4 print PDFs: two full-plan pages and one contact-card page, with every PDF page visually reviewed. Chromium/Firefox automation also covers selected editor and print-media behavior. Physical printing, real-device testing, long-plan pagination, and comprehensive accessibility remain pending; see the [bounded check record](docs/browser-check.md).
- Implemented: save JSON, edit it, and generate again; output can include sources and review dates supplied by the person completing the plan.
- Implemented: `init` / `template` creates an unreviewed draft in `private-input/` without modifying the repository example and preserves the original input-file CLI usage.
- Implemented: guided terminal creation with hidden validated prompts, and private bundles containing full HTML, portable text, contact/meeting cards, and a bounded integrity verifier.
- Implemented: a blank offline graphical studio with all schema-v1 fields, local JSON round trips, validation, reorderable lists, a live preview, and explicit JSON/printable downloads.
- Implemented: deterministic private revision reports with positional comparisons, canonical fingerprints, and read-only verification against both original plans.
- Planned: importing plan HTML, regional official-source verification, and real usage feedback.

The current format is JSON schema version 1, implemented with Python's standard library. Initial regional sources have not yet been selected or verified.
Use fictional data in public repositories and feedback; do not publish real contact details, addresses, or health information.

## Initial work and acceptance criteria

| Priority | Work | Evidence required for completion |
|---|---|---|
| P0 | Local editing, previewing, and printing | Runnable version, fictional example, instructions, and a print completeness check |
| P1 | Offline use and personal data protection | Offline execution record and checks that entered content was not sent to external servers |
| P1 | Export and reimport | JSON field preservation and invalid-input handling are implemented; arbitrary HTML reimport remains planned |
| P1 | Mobile use, keyboard operation, and English presentation | Check records for the target devices and input methods |
| P2 | Official-source maintenance | Source, version, review date, and applicable region recorded for every verified resource |

The first outcome milestone is a participant successfully finding contacts and meeting arrangements in a defined offline scenario,
then voluntarily providing feedback about difficulties without sensitive personal information.

## Possible future directions

- Backup recovery drills and verification reports for small organizations.
- Service-provider dependency inventories and alternative assessments.
- Original-source tracking and document version comparison.
- Tabletop exercises and records for network outages and other crisis scenarios.

These remain candidates. Each needs a clear user need, a review of existing tools, and a verifiable opportunity for improvement.

## Sources and evidence boundaries

The following official research leads await review. This repository has not rechecked their current content, attachments, or policy status:

- [Relevant Swiss government announcement](https://www.admin.ch/en/newnsb/zR3tvgIy1qIm)
- [SEPOS security policy strategy page](https://www.sepos.admin.ch/en/security-policy-strategy)

Future records should distinguish source statements, project interpretations, design proposals, and actual validation results,
with document versions, precise locations, and review dates. Policy approval, planned measures, legislation taking effect, and actual implementation are distinct states.
This project does not treat unreviewed measure numbers, dates, or summaries as confirmed policy facts.

## Contributing

Read the [roadmap](ROADMAP.md) and [contribution guide](CONTRIBUTING.md), choose a clearly scoped task, and collaborate through issues and PRs.
Contributions can include code, source corrections, language editing, exercise design, and usage feedback.
Each PR should describe the related problem, actual changes, validation evidence, and remaining work.
