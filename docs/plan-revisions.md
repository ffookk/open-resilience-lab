# Private plan revision review

Compare two schema-version-1 JSON plans locally before deciding what to review
with a household. The report shows added, removed, and changed content, including
old contact details or support needs that no longer appear in the revised plan.
All reports are private artifacts, not suitable for a public issue or PR.
If you need only section and operation counts, explicitly use
[`summarize-revision`](revision-summaries.md) to avoid retaining values and
fingerprints in the output. Aggregate counts still require private storage.

## Create and inspect a comparison

Use two saved plans that you intend to compare, with the older plan first:

```sh
python3 resilience_plan.py compare private-input/before.json private-input/after.json --output private-output/revision-01
python3 resilience_plan.py verify-review private-input/before.json private-input/after.json private-output/revision-01
```

For a fictional no-change demonstration without creating any personal input:

```sh
python3 resilience_plan.py compare examples/fictional-household.json examples/fictional-household.json --output private-output/fictional-review
python3 resilience_plan.py verify-review examples/fictional-household.json examples/fictional-household.json private-output/fictional-review
```

Open `review.html` in the new directory locally. The directory contains exactly:

| File | Purpose |
|---|---|
| `comparison.json` | Deterministic structured changes, section counts, input fingerprints, and entry counts |
| `review.html` | Self-contained before/after review with escaped literal values, screen and print styles |
| `manifest.json` | Completion marker with byte counts and SHA-256 digests of the two artifacts |

The HTML uses no JavaScript, browser storage, external assets, or active source
links. Source URLs are plain text. Use the browser Print menu and check pagination
before printing. One long fictional A4 report has a bounded
[PDF and keyboard-to-print check record](browser-check.md#2026-09-26-long-revision-report-and-keyboard-to-print-regression).
Other long-plan field combinations, Firefox PDF pagination, physical printing,
real-device behavior, and comprehensive accessibility remain unverified.

Both commands work offline using Python's standard library. Creation needs POSIX
private-storage support, as does the existing private-bundle workflow. New
directories use `0700`; new files use `0600`. Existing private parent directories
must already be owned by the current user with no group or other access. The
output must be a new directory below `private-output` in the current working
directory. Links in output paths, existing files or directories, and traversal
are rejected. There is no overwrite or force option. Neither input is modified.

Each input uses the existing strict plan validator and bounded loader: UTF-8
JSON, at most 256 KiB per file, schema version 1, supported fields only, valid
calendar dates, and no duplicate object keys. No report is created if either
input fails validation. Inputs follow the same loading rules as the plan
renderer; verification rejects linked artifact files and directory paths.

Success returns `0`; invalid arguments, input, output, or failed verification
return `2`; an interrupted operation returns `130`. Terminal diagnostics do not
include input values, filenames, paths, hashes, or change counts. Interrupted
creation attempts to remove only files created by that operation. After a
process crash or power failure, incomplete private output can remain; verify it
before use. A manifest does not make a multi-file directory update atomic.

## Exact comparison rules

The comparison is structural, case-sensitive, and directional:

- Object keys are visited in sorted order. JSON object key order and input
  formatting do not affect content comparisons.
- Every list is ordered. Entries at the same zero-based position are compared.
  Names, labels, source URLs, and duplicate values are never treated as stable
  identifiers. There is no move detection or similarity matching.
- A changed scalar produces one `changed` record with `before` and `after`.
  Adding or removing an entire optional field or a trailing list entry produces
  one `added` or `removed` record containing that complete subtree.
- Changes within paired list objects are reported at their individual field
  paths. A middle insertion or deletion can therefore change many subsequent
  positions and add or remove a trailing entry. A reorder can produce several
  changed records even if all entries still exist.
- Missing optional fields differ from explicitly empty lists. For example,
  absent `sources` versus `"sources": []` is one addition, although both have
  zero source entries in the metadata.
- Text is compared exactly. Whitespace inside strings, letter case, line breaks,
  and Unicode normalization differences are preserved and can cause changes.

For example, changing household entries from `[A, B]` to `[B, A]` compares A with
B at `/household/0` and B with A at `/household/1`. It does not assert that a
particular person moved. `[A, A]` to `[A]` removes the subtree at `/household/1`;
there is no claim about which real person the duplicate might represent.

`path` uses JSON Pointer notation: `/` separates object keys and array indices;
`~` and `/` within a key would be escaped as `~0` and `~1`. The current plan schema
has only fixed field names. A record has an `operation`, a `path`, and the relevant
`before` and/or `after` value. Missing values are omitted from JSON and labeled
**Not present** in HTML, rather than invented as empty strings or nulls.

Summary counts count records under these rules, not affected people, facts,
source verifications, or completed review tasks. The per-section counts sum to
the total. Metadata entry counts count list positions and include duplicates.
An identical report has no records and `summary.identical` is `true`.

## Fingerprints and verification

Comparison format 1 uses SHA-256 over each validated input serialized as UTF-8
JSON with sorted object keys, compact separators, literal Unicode, no non-finite
numbers, and no trailing newline. Array order and optional-field presence remain
unchanged. `canonical_bytes` is the byte count of this representation, not the
original file size. No filename, absolute path, generation time, or host identity
is stored. The two artifact files and manifest are deterministic for the same
plan contents and this implementation.

`verify-review` requires both original inputs and the review directory. It
recomputes the expected comparison and HTML from those inputs, then compares
exact bytes for the three fixed files. It never follows a filename supplied by
a manifest. It rejects missing or unexpected files, symbolic or hard-linked
artifacts, nonregular files, tampering, reordered JSON artifact keys or records,
modified whitespace in artifacts, and unsupported generated content. Reads are
bounded to 4 MiB per report artifact and 16 KiB for the manifest. Input JSON may
be reformatted without invalidating verification because its canonical content
is unchanged.

Verification is read-only and does not rewrite reports. It confirms consistency
with the supplied inputs and the currently supported renderer; it is not a
digital signature or a permanent cross-version archival guarantee. Keep both
original inputs and the generating tool version if exact reproduction matters.
The tool cannot protect against another process changing the directory during
or after inspection, or against someone replacing both inputs and reports.

## Review and privacy boundaries

The report never changes `reviewed_on` or `sources[*].verified_on`, inserts the
current date, approves a change, or marks household review complete.
`review_state` is always `not_verified_by_tool`, including for identical plans.
Format-valid dates remain user-entered claims. Decide together what to accept,
update the source JSON separately, and enter a review date only after the actual
review. The comparison does not provide emergency advice or validate sources.

Old and new values, fingerprints, and counts can all be sensitive. The output is
neither encrypted nor redacted. Git ignores the private directories, but that
does not prevent deliberate commits, cloud synchronization, browser extension
access, or printer retention. Keep both inputs, every review file, and any
printouts local and private. Use fictional data for feedback and public tests.
