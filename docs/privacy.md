# Privacy and contribution checks

## Measures in place

- Demonstrations and tests use fictional content; personal inputs and outputs belong in ignored local directories.
- Commits use a GitHub noreply email address; inspect author and committer details before committing.
- After creating a commit and before pushing, rerun `python3 scripts/privacy_check.py --history` so that checks include the new commit metadata.
- CI uses read-only repository permissions, receives no project secrets, and does not upload input, output, or test files as artifacts.
- GitHub Actions are pinned to specific commits; review dependency updates again before adopting them.
- Privacy findings display only rule names and file numbers, never matched values.

## Run before committing

```sh
git add <files-to-commit>
python3 scripts/privacy_check.py --history
git diff --cached --check
```

The checker covers tracked working-tree text, staged content, reachable historical text and filenames, and commit metadata. It detects common secret formats, private conversation links, local user paths, non-example email addresses, and sensitive directories. Binary files and symbolic links require manual handling.
Reproduce errors with a minimal fictional input first. Replacing names alone can leave private information in contact details, locations, or notes.

This heuristic check cannot identify every kind of personal information, custom credential, or image content. It does not inspect untracked files, GitHub issue/PR bodies, unreachable cloud history, platform retention records, or existing external copies. Manually review diffs and collaboration content before publishing.
Use `git diff --cached` in a trusted local terminal to inspect the actual staged changes. Do not paste diffs containing private values into public feedback.

## If a problem is found

Stop publishing changes and locate and remove the content locally first. Never paste original values into issues, PRs, discussions, screenshots, or logs. If a credential was exposed, revoke or rotate it before addressing repository history. Ordinary issues should record only a status update without sensitive values.
