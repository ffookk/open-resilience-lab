# Roadmap

Checked items have code or documentation deliverables. Unchecked items remain planned. Automated tests do not establish validation by real households, in disasters, or on all devices.

## PR 1: problem and evidence structure

- [ ] Extract problems suitable for open-source collaboration from available official security and civil-protection sources.
- [ ] Record the applicable region, original source, publication date, review date, and open questions for each problem.
- [x] Select a specific personal or household preparedness scenario: finding household-agreed contacts and meeting arrangements offline.

Acceptance: every specific policy or preparedness requirement can be traced to its regional source, with inferences recorded separately from document facts.

## PR 2: offline household plan generator prototype

- [x] Define the minimum necessary input and output structure (JSON schema version 1; see README).
- [x] Build a local JSON-editing-to-HTML prototype with print styles; validate browser pagination separately.
- [x] Implement offline generation: after obtaining the repository and Python, no dependency downloads are needed, and generation tests with sockets disabled pass.
- [x] Provide a fictional demonstration example.
- [x] Add local `init` / `template` commands with an unreviewed date placeholder, private file permissions, default overwrite refusal, replacement only of an unchanged draft, and preservation of the original generation command.
- [x] Check the earlier bilingual fictional example offline in one Chrome engine at desktop/narrow viewports and as A4 PDF; see the [check record](docs/browser-check.md).
- [x] Recheck the English fictional presentation at desktop and narrow viewports in one offline Chrome context.
- [x] Recheck the unchanged English fictional full plan and contact cards as headless Chromium 153 A4 print PDFs on 2026-09-22: two plan pages and one card page, all visually reviewed.
- [ ] Complete browser viewing with a real network disconnection, long-plan pagination, and physical printing checks.
- [x] Add a guided local terminal wizard with validated retries, optional fields, hidden prompts, cancellation, and exclusive private saving.
- [x] Export full HTML, portable text, and compact contact/meeting cards into a new private directory with a last-published integrity manifest and bounded verification.
- [x] Add a blank, self-contained graphical studio with complete schema-v1 editing, strict local JSON import, validated JSON round trips, reorderable lists, safe previews, and explicit printable exports.
- [ ] Import arbitrary plan HTML.

Current evidence: automated CLI tests, strict validation, HTML escaping, restricted file permissions, overwrite protection, absence-of-external-resources checks,
Chromium/Firefox editor and print-media regressions, and a 2026-09-22 desktop/narrow-viewport and A4 PDF review of the unchanged English fictional example in headless Chromium 153.
Output shows the region, review date, and sources supplied by the person completing the plan. Regional rules and real household outcomes remain unverified.
Full acceptance still requires viewing and printing in a genuinely disconnected environment, with pagination, accessibility, and usage feedback recorded.

## PR 3: verify usefulness

- [ ] Record target users' task completion time, omissions, and comprehension difficulties.
- [x] Add automated Chromium/Firefox keyboard editing, export, and print-media checks using fictional inputs.
- [ ] Check keyboard operation on real devices, physical print output, screen readers, and comprehensive manual accessibility.
- [ ] Revise the prototype based on observations and document limitations.

Acceptance: provide at least a reproducible usage scenario and before/after results. Completing a demonstration does not establish real disaster readiness or professional emergency certification.
