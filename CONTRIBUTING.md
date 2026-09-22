# Contributing

## Submit one clear, small change

1. Choose an independent problem from [ROADMAP.md](ROADMAP.md) and state the expected result.
2. Make the change on a new branch and use a clear commit message.
3. Open a pull request describing the purpose, sources, validation, and limitations.

Write repository documentation, examples, generated interface text, issues, PRs, discussions, release notes, and commit messages in English.
When changing CLI options, check `--help`, README examples, and default paths together so that instructions remain consistent.

## Evidence and data

- Prefer official documents, original data, or original research for factual records; retain precise source locations and review dates.
- Distinguish source statements, author inferences, unverified information, and experimental results.
- State the applicable date for time-sensitive content and retain necessary correction notes when updating it.
- Do not treat a conversation or an AI answer itself as evidence that a fact has been verified.
- Check licensing and redistribution terms before importing external material; prefer links and the minimum necessary excerpts.

## Privacy and validation

- Use fictional or lawfully public examples. Do not commit API keys, credentials, real household contact details, or private conversations.
- Data changes should be traceable and reviewable; code changes should include appropriate execution instructions and validation results.
- When changing input fields, check omission, empty values, types, lengths, and the corresponding HTML display.
- Clearly label work that has not been implemented or verified; do not describe plans as completed results.
- For browser problems, record the exact version, viewport size, and fictional sample. Narrow-screen screenshots do not establish physical mobile-device validation.

## Automated checks

Before committing, read the [privacy guide](docs/privacy.md), run the validation commands in the README, and run `python3 scripts/privacy_check.py --history`. The PR Checks workflow runs privacy checks, a Python/OS unit-test matrix with explicit Node support, documented fictional examples, and Chromium/Firefox regression tests. See the [browser check guide](docs/browser-check.md) for local commands and coverage limits. The required `validate` check succeeds only when the matrix and browser jobs both succeed.

`main` currently requires a PR and a passing `validate` check, including for administrators. Commit on a working branch; force pushes and deletion of the main branch are prohibited. Automated checks do not replace reviews of facts, privacy, or usefulness.

Run `python3 scripts/check_english.py` after staging changes. CI checks current tracked text, including decoded JSON values, for CJK scripts. This guard is not a general language classifier; manually review all public wording and GitHub collaboration text for English. Historical revisions are outside this check.
