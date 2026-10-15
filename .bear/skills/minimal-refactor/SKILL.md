---
name: minimal-refactor
description: Simplify existing code while preserving behavior and public interfaces. Use for removing duplication, reducing complexity, 精简代码、重构、去除重复、过度设计.
---

# Minimal refactor

Task: $ARGUMENTS

Reduce a concrete maintenance burden while preserving the behavior the user relies on.

- Identify the repeated logic, dead branch, or unnecessary layer and inspect its callers before editing. State the behavior that must remain stable.
- Prefer deleting redundant code, using an existing helper, or using the standard library over adding a dependency or abstraction.
- Preserve public signatures, CLI output relied on by callers, configuration semantics, and error handling unless the user requested a change. Keep behavioral bug fixes distinct and explain them.
- Do not remove an apparently unused public entry point solely because an internal search finds no caller. Check documented or external use where relevant.
- Make the smallest coherent change; avoid unrelated renaming, formatting, and future-proof extension points.
- Run existing checks for the affected behavior. Add tests only for a meaningful gap exposed by the refactor, rather than coupling tests to the new structure.

Report what became simpler, how behavior was checked, and any compatibility uncertainty.
