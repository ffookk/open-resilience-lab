# Private revision summaries

Use `summarize-revision` when you need to retain only how many changes occurred
in each plan section, without saving the old and new values or input fingerprints.
This is an explicit alternative to a full revision review. It still processes
both original plans locally, and the resulting counts can disclose information.
Keep the summary private; it is not anonymous or automatically safe to publish.

## Create a summary

```sh
python3 resilience_plan.py summarize-revision private-input/before.json private-input/after.json --output private-output/revision-counts.json
```

Without `--output`, the destination is `private-output/revision-summary.json`.
The destination must be a new `.json` file below `private-output` in the current
working directory. Existing output is never overwritten, and there is no force
option. Choose a different filename for another summary.

For a fictional no-change demonstration:

```sh
python3 resilience_plan.py summarize-revision examples/fictional-household.json examples/fictional-household.json --output private-output/fictional-counts.json
```

The command writes exactly one JSON summary. It does not create a full review,
HTML, manifest, or additional sidecar file. It prints a fixed success message,
without counts, paths, filenames, hashes, or plan text. No browser is launched.
Previously created full reviews remain unchanged and may still contain private
old and new values.

## What the file contains

All field names and text values are fixed by the summary format. Only numeric
change counts vary with the inputs:

| Field | Meaning |
|---|---|
| `summary_format` | Integer `1` |
| `plan_schema_version` | Integer `1` |
| `matching` | Fixed string `ordered-index` |
| `review_state` | Fixed string `not_verified_by_tool` |
| `totals` | Counts named `added`, `removed`, `changed`, and `total` |
| `sections` | The same four counts for each fixed plan section |

The fixed sections are `title`, `region`, `reviewed_on`, `contacts`,
`meeting_points`, `household`, `notes`, and `sources`. A section name is a schema
label, never the entered title, region, or review date. All sections appear,
including those with zero changes. Counts are nonnegative integers; each total
is the sum of its three operation counts, and section counts sum to the overall
counts. Equal plans produce zeros throughout, without implying completed review.

The file contains no entered values, record names, individual paths or indices,
input filenames, dates, entry counts, IDs, fingerprints, or generation timestamp.
It does not identify either original plan. Different input pairs with identical
change patterns produce identical summary bytes, even if their private details
and unchanged list lengths differ. The summary cannot prove source identity,
reproduce a plan, or replace a full review's before/after evidence.

## Counting rules

Counts use the same validated comparison rules as
[private plan revision reviews](plan-revisions.md#exact-comparison-rules):

- Lists are compared by zero-based position. Names and duplicate values are
  never used to infer identities or moves. Inserting, removing, or reordering
  entries can produce multiple changed positions.
- A changed scalar contributes one `changed` count. An added or removed entire
  optional field or trailing list entry contributes one `added` or `removed`
  count, even when that subtree contains several fields.
- Missing optional fields differ from explicitly empty lists. Text is compared
  exactly, including case, whitespace, and Unicode normalization differences.
- Counts describe structural change records, not affected people, household
  readiness, source verification, or completed tasks. No review date is changed.

The existing single-plan `--summary` option reports entry counts after validating
one plan. `summarize-revision` instead compares two plans and saves change counts.
`verify-review` applies to the full three-file review format, not this summary.
To recalculate counts, run `summarize-revision` with both inputs and a new output.

## Validation, storage, and limits

Both inputs retain the existing UTF-8 JSON, 256 KiB per-file limit, and complete
schema-v1 validation. Invalid or duplicate fields, invalid dates, and malformed
inputs are rejected before any output directory is created. Neither input is
modified. The workflow runs offline with Python's standard library and requires
the same POSIX private-storage support as other private exports.

New files use `0600`; new directories use `0700`. Existing private parents must
be owned by the current user with no group or other access. Destination links,
linked parent directories, traversal, unexpected file extensions, and existing
files or directories are rejected. The writer publishes a completed file through
an exclusive link and never replaces a competing output. Handled write failures
and interruptions clean up only files owned by that operation. A process crash
can leave a private pending file; check local storage before relying on output.

Exit codes are `0` for success, `2` for invalid input/arguments or save failures,
and `130` for interruption. Diagnostics contain no supplied values or paths.
If interrupted during publication, inspect the destination locally: a complete
file may already exist even though the command did not report success.

This reduces retained detail, not the sensitivity of the original plans or every
possible inference from counts. For example, a household-section count reveals
that something in that section changed. Local file metadata, chosen filenames,
backups, operating systems, and synchronization services remain outside this
content-minimization feature. The summary is neither encrypted nor anonymous;
there is no upload or public sharing action. Use fictional data in public issues
and retain real summaries only in trusted private storage.
