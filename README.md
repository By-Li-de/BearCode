# BearCode

A small Python agent harness for OpenAI-compatible and Anthropic-compatible models.
It combines a tool loop, permission checks, MCP, sub-agents, memory, sessions, and reusable skills.

## Quick start

Python 3.11+ is recommended. MCP servers may also need Node.js.

```bash
git clone https://github.com/By-Li-de/BearCode.git
cd BearCode
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set your provider's credentials and model in `.env`, for example:

```dotenv
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL=your-model-or-deployment
```

For Anthropic-compatible endpoints, use `APIKEY`, `API` (a URL ending in `/anthropic`),
and `MODEL`, or the native `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` variables.
Real `.env` files and their backups are ignored by Git.

```bash
python -m agents.main                         # interactive session; type exit to quit
python -m agents.main "Explain this project"  # one task
python -m agents.main --plan "Plan a refactor"
python -m agents.main --resume
```

## Everyday skills

Use `/skills` to list installed skills. These project skills support English and Chinese requests
and can also be invoked directly in an interactive session:

| Command | Purpose |
| --- | --- |
| `/debugging <failure>` | Reproduce a failure, find its cause, and verify a focused fix |
| `/test-and-verify <change>` | Check behavior with relevant tests and report coverage gaps |
| `/explain-project <question>` | Trace architecture or a feature through current source |
| `/minimal-refactor <scope>` | Simplify code while preserving behavior |
| `/git-commit <scope>` | Prepare a focused commit; pushing requires user authorization |

The existing `code_review` skill handles code review requests automatically.
Restart a running session after editing skill files to refresh the skill cache.

## Skill evolution

Feedback and model skill tools **stage candidates instead of changing active skills**.
Review a candidate, compare it with its previous version, then explicitly accept it:

```text
/skill-candidates
/skill-diff <id>
/skill-eval <id> examples/skill_eval.json
/skill-accept <id>
/skill-rollback <id>
/skill-reject <id>
```

Edit [the example cases](examples/skill_eval.json) to match the proposed rule.
Each case supplies a `prompt` plus `exact`, `must_include`, or `must_not_include` checks.
Evaluation makes two model requests per case (1-20 cases): baseline and candidate.
Acceptance requires every candidate check to pass, a strict score improvement,
and the same selected model. These are prompt-only checks, not end-to-end coding benchmarks.
Reports and before/after versions stay in the ignored `.bear/skill-evolution/` directory.
Acceptance and rollback refuse to overwrite active files changed since the recorded version.

`/extract_now [hint]` stages feedback immediately. `/skills` and `/skill-stats` inspect skills.
`/skill-create` and `/skill-evolve` remain explicit manual authoring commands.
Set `BEAR_AUTO_SKILL_EVOLUTION=0` to disable background extraction.
Usage-based automatic pruning is off unless `BEAR_SKILL_AUTO_PRUNE=1` is explicitly set.

## Configuration and permissions

See [.env.example](.env.example) for context/output limits and optional token prices.
Unknown model names default to 32,768 context tokens and 4,096 output tokens; override
`BEAR_CONTEXT_WINDOW` and `BEAR_MAX_OUTPUT_TOKENS` for your deployment.
`--max-cost` requires both `BEAR_INPUT_PRICE_PER_MTOK` and `BEAR_OUTPUT_PRICE_PER_MTOK`.
Costs are estimates; individual requests can exceed the remaining budget.

- `--plan`: read-only, except for its plan file; activation and rollback are blocked.
- `--accept-edits`: automatically allow project edits; Shell and untrusted MCP calls need approval.
- `--dont-ask`: reject actions requiring confirmation. `--yolo` skips permission checks.
- Permissions are application-level controls, not an operating-system sandbox.

Project skills live in `.bear/skills/`; user skills in `~/.bear/skills/`.
Configure MCP in `.mcp.json` or `.bear/settings.json`; requests default to 60 seconds
and support a per-server `requestTimeout` in seconds.
`/memory`, `/compact`, `/clear`, and `/cost` manage session context.

## Development

```bash
python -m unittest discover -s tests -v
```

Tests use mocked model responses and local MCP subprocesses; no real key or API credits are needed.
The runtime is in `agents/agent.py`, tools in `agents/tools.py`,
and candidate evaluation/rollback in `agents/skill_validation.py`.
