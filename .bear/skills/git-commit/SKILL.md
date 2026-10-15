---
name: git-commit
description: Prepare and create a focused Git commit, with an optional authorized push. Use for commit preparation, 提交代码、整理提交、推送代码.
---

# Git commit

Task: $ARGUMENTS

Keep the commit limited to the user's intended changes and preserve unrelated work.

- Inspect the working tree, staged and unstaged diffs, current branch, and remote. If unrelated edits are present, stage only the requested paths or hunks; avoid blanket staging.
- Check for credential files, local configuration, generated output, and private notes before staging. Use ignore checks and secret detection that reports filenames or locations without printing sensitive values. Do not assume adding a file to `.gitignore` removes already tracked content.
- Run checks appropriate to the diff and inspect the staged diff before committing. Describe the resulting behavior and validation in the commit message.
- Create a commit when requested. Push only when the user's current or prior instructions authorize it; inspect the destination first. Skill invocation alone does not authorize a push, release, or deployment.
- Never discard unrelated edits, rewrite published history, or force-push as part of routine preparation. If a push is rejected, inspect the divergence before choosing a recovery that could affect others' work.
- Verify the commit and, when pushing, confirm that the intended remote branch points to it. If publishing fails, report the local commit and the actual failure.

For a preparation-only request, leave a reviewable staged change or proposed file list and message without publishing.
