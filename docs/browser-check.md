# Browser and print check record

## Automated regression coverage

The Checks workflow now includes a portable browser suite in `tools/browser`.
It generates a fresh blank Studio, full plan, and printable cards from
`examples/fictional-household.json`, adding only fixed fictional multiline and
literal-markup text. Chromium and Firefox each exercise keyboard editing,
first-error focus through collapsed fields, JSON import/export, explicit save
confirmation, invalid-import and cancelled-reset preservation, and HTML/card
downloads. Preview filters and display preferences must leave exports complete.

It also generates a fictional revision review with one added household entry and
one changed notes field containing literal hostile markup. Both engines check
the record summary, before/after value fidelity, inert markup, empty browser
storage, absence of scripts or external resources, and no horizontal overflow
at 1280- and 360-pixel widths. Emulated print media keeps the change records and
hides the skip link. A separate long fictional notes comparison checks all 241
lines per side (240 numbered lines plus an unbroken trailing string), widths
1280/360/320, keyboard activation of the skip link, main focus, unique IDs,
article/region names, and table/heading semantics. Keyboard focus remains visible
on screen, including emulated forced colors, and its outline is suppressed only
for print. These automation checks do not establish screen-reader usability or
review PDF pagination; the bounded PDF observation below is separate.

The suite checks multiline text in Python-generated and Studio-exported pages
under screen and emulated print media. It checks that Studio editor controls and
the JSON inspector are hidden for printing, and that a narrow Studio viewport has
no horizontal overflow. Fresh browser contexts are offline; external page
requests are blocked and counted, with any observed request failing the test.
No screenshots, traces, videos, plans, or browser artifacts are uploaded by CI.
Generated fictional files are removed after each test.

Run from the repository root after installing Python 3.10 or newer and Node 24:

```sh
npm --prefix tools/browser ci --ignore-scripts --no-audit --no-fund
cd tools/browser
npx --no-install playwright install chromium firefox
npm test
```

Linux runners install browser system libraries with
`npx --no-install playwright install --with-deps chromium firefox`.
The suite calls `python3` and receives fictional fixture documents on standard
output; it writes only fixed filenames in its owned temporary directory.
Browser binaries and pinned Playwright packages are development tools; generating or using a plan still
requires no Node installation or third-party Python runtime package.

CI also runs the Python suite on Ubuntu with Python 3.10 through 3.14 and on
macOS with Python 3.14. Each unit-test job explicitly installs Node 24 for the
JavaScript parity/state tests. The required `validate` job runs after the matrix
and browser jobs and fails unless both report success, including when a
prerequisite is skipped or cancelled.

These automated assertions do not establish physical printing, PDF pagination,
screen-reader usability, manual accessibility review, real household outcomes,
or a network audit of the entire browser process. Historical observations below
remain limited to their stated samples and dates.

## 2026-09-26: long revision report and keyboard-to-print regression

A fictional notes-only revision with 240 numbered before lines and 240 numbered
after lines was rendered in headless Chromium 153.0.8010.12 with Playwright
1.63.0 and Node 24. The notes were within the existing 4000-character field
limit. The browser activated **Skip to changes** with Tab and Enter before
switching to print media, then generated A4 PDFs with browser headers/footers
disabled. No real household information was used.

Before the repair, the main region's visible keyboard focus outline also
printed. On continuation pages the fragmented 3-pixel outline crossed the top
line of text. Both Chromium and Firefox regression checks failed because the
focused main element still had a solid outline under print media. The repair
suppresses that outline only for print; it leaves screen keyboard focus intact.

After the repair, the fictional A4 PDF still had eight pages and all 480 unique
line markers extracted exactly once. Every page was rasterized and inspected;
the heavy continuation-page rules were absent, with no observed text clipping,
overlap, or missing line markers in this sample. The long browser fixture also
passed keyboard, semantic, narrow-layout, and screen/print content-preservation
checks in Chromium and Firefox 155.0. External page requests were blocked and
none were observed. Generated PDFs, images, and test artifacts stayed local.

This is one synthetic long-notes case, not a guarantee for every possible field
combination, paper size, or browser. Firefox PDF pagination, physical printing,
real-device behavior, screen readers, comprehensive manual accessibility, and
real household review remain unverified.

## 2026-09-22: English fictional plan and card PDFs

The unmodified `examples/fictional-household.json` was rendered as a full plan
and contact/meeting cards with the Python generator. Headless Chromium
153.0.8010.12, driven by Playwright 1.63.0 and Node 22.22.3, produced A4 PDFs with
explicit print-media emulation and browser headers/footers disabled. Every PDF
page was rasterized and visually reviewed: the full plan had two pages and the
cards had one page. No clipped or overlapping text or split card was observed.
The household-notes heading stayed with its paragraph; a wrapping card-footer
date remained fully readable. Screen navigation was absent from the print PDFs.

The same generated pages were captured at 1280 x 900 and 390 x 844 with no
horizontal overflow detected. The offline page contexts recorded zero external
HTTP/HTTPS requests and no JavaScript page errors. These artifacts remained
local and were not uploaded to CI or the repository.

This record covers one unchanged fictional example and one Chromium build.
The separate Firefox tests exercise browser interactions and emulated print
styles, not Firefox PDF pagination. Long-plan pagination, physical printing,
real-device behavior, screen readers, comprehensive manual accessibility, and
real household outcomes remain unverified. Repeat pagination review after
presentation changes; print-media emulation must be selected explicitly when
switching from screen screenshots to PDF generation.

## 2026-09-20: English-only screen check

The translated fictional example was regenerated and opened in an offline Chrome 153.0.8010.53 context. Desktop (1280 x 900) and narrow (390 x 844) screenshots were visually reviewed: all sections were visible, text wrapped without observed clipping, and neither viewport had horizontal overflow. The document declares `lang="en"`, and no CJK text was found in the rendered body.

The page initiated 0 HTTP/HTTPS requests and contained 0 scripts or external resource elements. This check covered one fictional example and one browser engine. At that date, PDF pagination, physical printing, screen readers, and maximum-length content were not rechecked for the English presentation. The 2026-09-22 record above supersedes only the fictional-sample English PDF gap; the earlier bilingual PDF result below remains historical.

## 2026-09-20: historical single-browser check of the fictional plan

This record covers the earlier bilingual presentation, before the English-only update. Its two-page result does not establish the current English layout or pagination; repeat the checks after presentation changes.
HTML was generated from `examples/fictional-household.json` and opened in a fresh offline browser context. All data was fictional or placeholder text.

| Check | Recorded result |
|---|---|
| Browser | Google Chrome 153.0.8010.53, headless |
| Desktop viewport | 1280 × 900; no horizontal overflow detected |
| Mobile-sized viewport | 390 × 844; no horizontal overflow detected |
| Page-initiated HTTP/HTTPS requests | 0 |
| Page scripts and external resource elements | 0 |
| Print output | Browser-generated A4 PDF, 2 pages; browser headers and footers disabled |
| Visual page check | Text legible on both pages; no observed clipping, overlap, or missing sections |
| PDF content check | Plan sections extractable; no local file paths or file URLs found |

Some characters in extracted PDF text used compatibility glyphs. Apply Unicode NFKC normalization before comparing headings; the visual rendering was correct in that check.

## Reproduce the check

1. Generate the fictional HTML using the README demonstration command.
   If the destination exists, choose another with `--output private-output/browser-check.html`; check the purpose of existing files before rerunning.
2. Open the local file offline in a separate browser profile and inspect the title, contacts, meeting arrangements, household members, notes, and sources.
3. Inspect desktop and narrow viewports for horizontal scrolling and clipped content.
   Create a separate fictional sample for long-content checks and record its results separately; one passing sample does not establish that all maximum-length field combinations fit.
4. Print to A4 PDF with browser headers and footers disabled; inspect each page, pagination, and extracted text.
   Record changes to paper size, scaling, or margins and recheck pagination instead of reusing the two-page result above.
5. Save screenshots and PDFs only from fictional samples in ignored local directories. Never commit personal plans.

## What this check does not cover

This was a check of one browser engine and one fictional sample. Cross-browser use, screen readers, physical printing, real household exercises, and regional policy acceptance remain unverified. Observing page requests is not a network audit of the entire browser process. Follow-up work is tracked in Issue #3.
