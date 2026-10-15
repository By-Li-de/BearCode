---
name: explain-project
description: Explain an unfamiliar repository's architecture and trace a feature through actual code. Use for project onboarding, code flow, 理解项目、项目结构、架构、调用链.
---

# Explain a project

Task: $ARGUMENTS

Build a focused map from the current source. This workflow is read-only unless the user also requests edits.

- Start with the README, dependency manifest, and executable entry point. Follow the requested feature through its callers, state, and side effects rather than reading every file.
- Separate implemented behavior from comments, planned features, and inferred intent. Verify claims against the functions that execute them.
- Explain the main components and one concrete request's path through them. Cite relevant files and symbols so the user can continue exploring.
- Mention configuration names and loading locations when they explain behavior; do not read or reproduce credential values.
- If the user asks where to add a feature, identify the smallest suitable extension point and relevant checks. Avoid turning the explanation into a speculative rewrite proposal.

Match the user's language and level of detail. Use a short diagram only when it clarifies a nontrivial flow.
