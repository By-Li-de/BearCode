---
name: test-and-verify
description: Verify a code change using focused tests and observable acceptance criteria. Use for regression testing, checking a patch, 测试、验证改动、回归验证.
---

# Test and verify

Task: $ARGUMENTS

Choose checks from the behavior at risk and the repository's existing test setup.

- Inspect the diff and nearby tests. Identify the observable result and the important failure or boundary case before adding tests.
- Run the smallest relevant existing check first. Add a regression when it protects meaningful behavior; avoid assertions that merely repeat implementation details or match documentation wording.
- Use existing test tools and local fixtures. Keep external APIs, paid model calls, production data, and publishing out of routine checks unless the user has authorized them.
- A mock can verify orchestration but cannot prove that a real provider, browser, or subprocess integration works. State which boundary was exercised.
- Classify failures as introduced by the change, pre-existing, or blocked by the environment using evidence. Do not weaken assertions or silently rewrite product behavior to make the suite pass.
- Broaden checks when a shared runtime path changes or a failure reveals additional risk. Avoid repeatedly running the same successful checks without a new reason.

Report exact commands, results, and untested behavior. Say explicitly when a check was not run; syntax checking alone does not establish functional correctness.
