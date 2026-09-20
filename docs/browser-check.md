# Browser and print check record

## 2026-09-20: English-only screen check

The translated fictional example was regenerated and opened in an offline Chrome 153.0.8010.53 context. Desktop (1280 x 900) and narrow (390 x 844) screenshots were visually reviewed: all sections were visible, text wrapped without observed clipping, and neither viewport had horizontal overflow. The document declares `lang="en"`, and no CJK text was found in the rendered body.

The page initiated 0 HTTP/HTTPS requests and contained 0 scripts or external resource elements. This check covered one fictional example and one browser engine. PDF pagination, physical printing, screen readers, and maximum-length content were not rechecked for the English presentation; the earlier two-page PDF result below remains historical.

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
