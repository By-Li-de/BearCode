---
name: debugging
description: Diagnose and fix reproducible failures, exceptions, crashes, and wrong results. Use for debugging, bug fixes, 调试、报错、崩溃、修复故障.
---

# Debugging

Task: $ARGUMENTS

Trace the observed failure to its cause before changing code.

- Read the failing command, traceback, relevant implementation, and callers. Distinguish observations from hypotheses; preserve the original error for comparison.
- Reproduce with the smallest input or existing test that exercises the failure. If reproduction is blocked, state the missing evidence and inspect the relevant path without inventing a result.
- Check assumptions at the failing boundary, such as input shape, environment loading, permissions, or async cleanup. Avoid blanket dependency upgrades, broad exception suppression, and unrelated rewrites.
- Apply a focused fix when requested. For a diagnosis-only request, explain the cause and proposed correction without editing.
- For a behavioral fix, prefer a regression that fails before the change and passes afterward. Run the nearest relevant existing checks and stop expanding the patch once the cause is resolved.

Report the cause, changed behavior, checks actually run, and any remaining uncertainty. Keep secrets out of reproduced logs and examples.
