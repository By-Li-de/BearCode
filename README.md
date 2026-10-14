# Bear Code

Bear Agent 是一个基于 Python 实现的 **自进化 Harness Agent**。它不是简单的命令行聊天工具，而是一个可运行、可阅读、可扩展的本地 Coding Agent Runtime：统一编排大模型推理、工具调用、文件编辑、Shell 执行、权限控制、长期记忆、Skills、自进化、MCP 外部工具、子 Agent 和会话恢复。

项目重点是 **Harness**：模型只负责推理和提出工具调用意图，真正的环境操作由 Bear Code Runtime 统一做权限判断、工具执行、结果回写、上下文压缩和经验沉淀。它适合学习 Claude Code 类工具的底层机制，也适合作为个人 Coding Agent、项目分析助手或领域 Agent 的二次开发基础。

## 核心亮点

- **自进化 Harness Agent**：从用户反馈中自动抽取可复用规则，新增或合并到 [SKILL\.md](http://SKILL.md)，让 Agent 能随着使用持续沉淀能力。

- **完整 Agent Loop**：模型请求、tool call 解析、权限检查、工具执行、tool result 回写、继续推理、会话保存形成闭环。

- **OpenAI / Anthropic 双协议**：支持 OpenAI\-compatible 和 Anthropic\-compatible 接口，便于接入不同模型服务或代理网关。

- **工具系统与权限控制**：支持读写文件、精确编辑、代码搜索、Shell 命令、Skill 调用、子 Agent 和 MCP 工具；Plan Mode 下阻断写操作和 Shell。

- **Skills 体系**：通过项目级和用户级 [SKILL\.md](http://SKILL.md) 保存可复用任务方法，支持检索、调用、inline / fork 执行和版本化演化。

- **长期 Memory**：按项目路径 hash 隔离记忆，保存用户偏好、项目背景、历史决策和参考资料。

- **MCP 外部工具扩展**：自研 stdio JSON\-RPC MCP Client，把外部 MCP Server 工具包装为 mcp\_\_server\_\_tool。

- **子 Agent**：支持 explore、plan、general 以及自定义子 Agent，用隔离上下文完成探索、规划或局部任务。

- **会话恢复和上下文压缩**：自动保存 session，支持 \-\-resume、/compact，并对大工具结果做截断或持久化。

## 项目架构

核心运行链路：

```Plain Text
用户输入
  -> agents/main.py
  -> Agent.chat()
  -> 构建 Prompt / 检索 Skills / 预取 Memory / 初始化 MCP
  -> 调用 OpenAI-compatible 或 Anthropic-compatible 模型
  -> 模型返回文本或 tool call
  -> Harness 做权限检查
  -> 执行工具 / Skill / MCP / 子 Agent
  -> tool result 回写模型
  -> 保存 Session
  -> 后台执行 Skill usage tracking 和 online skill evolution
```

## 目录结构

```Plain Text
BearCode/
├── agents/
│   ├── main.py                    # CLI 入口、REPL、参数解析
│   ├── agent.py                   # Agent Runtime、模型调用、工具调度、上下文压缩
│   ├── tools.py                   # 内置工具和权限系统
│   ├── prompt.py                  # System prompt 动态构建
│   ├── skills.py                  # Skills 加载、检索、执行、创建和演化封装
│   ├── online_skill_evolution.py  # 在线 Skill 抽取和 add/merge/discard 决策
│   ├── skill_evolution.py         # Skill 落盘、版本快照、审计统计
│   ├── memory.py                  # 长期记忆系统
│   ├── mcp_client.py              # MCP stdio JSON-RPC 客户端
│   ├── subagent.py                # 子 Agent 配置
│   ├── session.py                 # 会话保存与恢复
│   └── ui.py                      # 终端 UI 输出
├── .bear/
│   ├── skills/                    # 项目级 Skills
│   └── skill-evolution/           # Skills 自进化审计产物
├── Dockerfile
├── requirements.txt
└── README.md
```

## 快速启动

项目仓库：[By-Li-de/BearCode](https://github.com/By-Li-de/BearCode)

### 准备环境

推荐环境：

- Python 3\.11\+

- macOS / Linux

- Git

- ripgrep，可选但推荐

- 一个 OpenAI\-compatible 或 Anthropic\-compatible 模型接口

获取项目并安装依赖：

```Plain Text
git clone https://github.com/By-Li-de/BearCode.git
cd BearCode
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 配置 \.env

先执行 `cp .env.example .env`，然后只在本地 `.env` 中填写真实 key。`.env`、其备份和本地笔记目录 `doc/` 均已被 Git 忽略；提交到仓库的 `.env.example` 仅保留占位示例。

项目会自动读取当前目录或父目录中的 \.env。

Anthropic\-compatible 示例：

```Plain Text
APIKEY=sk-your-api-key
API=https://your-host/anthropic
MODEL=claude-sonnet-4-6
```

OpenAI\-compatible 示例：

```Plain Text
OPENAI_API_KEY=sk-your-api-key
OPENAI_BASE_URL=https://your-host/v1
MODEL=gpt-4o
```

也可以使用通用变量：

```Plain Text
APIKEY=sk-your-api-key
API=https://your-host/v1
MODEL=deepseek-chat
```

协议判断规则：

- API 或 \-\-api\-base 路径包含 /anthropic 时，按 Anthropic\-compatible 调用。

- 否则有 OpenAI base URL 时，按 OpenAI\-compatible 调用。

- \-\-model 会覆盖 \.env 中的 MODEL。

### 启动 REPL

模型限制与费用估算可在本地 `.env` 中配置：

|变量|用途|
|---|---|
|`BEAR_CONTEXT_WINDOW`|当前模型或部署的上下文长度；未识别的模型名称默认使用 32768 tokens|
|`BEAR_MAX_OUTPUT_TOKENS`|每次请求的输出上限；未识别的模型名称默认使用 4096 tokens，必须小于上下文长度|
|`BEAR_OPENAI_OUTPUT_PARAMETER`|OpenAI-compatible 输出限制字段，可选 `max_tokens` 或 `max_completion_tokens`；GPT-5、GPT-6 和 o1/o3/o4 名称默认使用后者，自定义部署可显式覆盖|
|`BEAR_INPUT_PRICE_PER_MTOK`|当前模型每百万输入 tokens 的美元价格|
|`BEAR_OUTPUT_PRICE_PER_MTOK`|当前模型每百万输出 tokens 的美元价格|

请按实际提供商和部署填写限制与价格。未配置价格时仍能正常运行，只显示 tokens 和费用不可估算；使用 `--max-cost` 时必须配置两项价格，免费本地模型可填 `0`。费用统计包含主请求、记忆/Skill 辅助请求、压缩和子 Agent 已报告的用量；缓存等特殊计费仍按配置的输入单价估算。预算在模型调用前后检查，单次请求及同时进行的辅助请求仍可能超过剩余额度，最终以提供商账单为准。

```Plain Text
python3 -m agents.main
```

启动后直接输入任务，例如：

```Plain Text
阅读这个项目，告诉我 Agent Loop 是怎么跑起来的
```

### 执行一次性任务

```Plain Text
python3 -m agents.main "总结这个项目的目录结构和核心模块"
```

### 使用 Plan Mode

Plan Mode 适合重构、复杂修复和多文件修改。它会先只读分析和写计划，用户审批后再执行。

```Plain Text
python3 -m agents.main --plan "分析 Skills 检索逻辑应该如何优化"
```

REPL 中也可以输入：

```Plain Text
/plan
```

### 恢复最近会话

```Plain Text
python3 -m agents.main --resume
```

## 如何让项目自动沉淀并进化 Skills

Bear Code 的核心特色是 **自进化 Skills**。它可以从用户明确反馈中抽取未来可复用的规则，并自动新增或合并到项目级或用户级 [SKILL\.md](http://SKILL.md)。

### 开启自动自进化

默认 BEAR\_AUTO\_SKILL\_EVOLUTION 是开启的。为了明确配置，建议在 \.env 中写：

```Plain Text
BEAR_AUTO_SKILL_EVOLUTION=1
BEAR_AUTO_SKILL_TARGET=project
```

含义：

- BEAR\_AUTO\_SKILL\_EVOLUTION=1：启用在线 Skill 自进化。

- BEAR\_AUTO\_SKILL\_TARGET=project：自动新增的 Skill 写入当前项目 \.bear/skills/。

如果希望沉淀为所有项目共享的个人 Skill：

```Plain Text
BEAR_AUTO_SKILL_TARGET=user
```

对应路径：

```Plain Text
project: <project>/.bear/skills/<skill_name>/SKILL.md
user:    ~/.bear/skills/<skill_name>/SKILL.md
```

### 用允许写入的权限模式启动

后台自动写入 Skill 需要当前权限模式允许写文件。推荐使用：

```Plain Text
BEAR_AUTO_SKILL_EVOLUTION=1 \
BEAR_AUTO_SKILL_TARGET=project \
python3 -m agents.main --accept-edits
```

也可以使用更激进的模式：

```Plain Text
python3 -m agents.main --yolo
```

不建议长期默认使用 \-\-yolo，因为它会跳过确认。日常推荐 \-\-accept\-edits，既能让后台 Skill 写入正常发生，又不会绕过所有权限判断。

### 给出可复用反馈

自进化不是把每一句话都写成 Skill。它只适合沉淀稳定、明确、未来同类任务仍适用的规则。

不太适合沉淀：

```Plain Text
帮我写一篇 500 字政府报告。
```

适合沉淀：

```Plain Text
以后写政府报告、工作汇报、调研材料时，默认先给可直接使用的初稿，不要连续追问；结构按“标题、背景、主要情况、问题分析、工作举措、下一步计划”组织，语言要正式克制。
```

适合演化已有 Skill：

```Plain Text
以后这类政府报告还要加入关键数据指标，不能只写概念性表述。
```

### 自进化链路如何工作

```Plain Text
第 N 轮用户任务
  -> Agent 输出结果
  -> 保存 pending extraction window
第 N+1 轮用户反馈
  -> 合并进上一轮 window
  -> online_ingest()
  -> Extractor 抽取候选 Skill
  -> Maintainer 判断 add / merge / discard
  -> create_skill_file() 或 evolve_skill_file()
  -> 写入 SKILL.md
  -> 记录 provenance、usage stats 和版本快照
```

核心文件：

```Plain Text
agents/agent.py
agents/online_skill_evolution.py
agents/skills.py
agents/skill_evolution.py
```

审计产物：

```Plain Text
.bear/skill-evolution/usage.jsonl
.bear/skill-evolution/online_provenance.jsonl
.bear/skill-evolution/online_skill_provenance.json
.bear/skill-evolution/skill_usage_stats.json
.bear/skill-evolution/history/
.bear/skill-evolution/pruned/
```

### 手动触发当前窗口抽取

如果你想立即把当前对话窗口送入自进化链路，可以在 REPL 中执行：

```Plain Text
/extract_now 这是一个可复用的写作规则
```

在 default 模式下，显式抽取会走交互确认；在 \-\-accept\-edits 或 \-\-yolo 下会更顺畅。

### 手动创建 Skill

```Plain Text
/skill-create government-report-writing | 政府报告写作规范 | 用户要求写政府报告、工作汇报、调研报告、公文材料时使用 | 默认按标题、背景、问题、举措、成效、下一步计划组织内容；语言正式克制；信息不足时先生成可用初稿，并在末尾列出待补充信息。
```

### 手动演化 Skill

```Plain Text
/skill-evolve government-report-writing 以后政府报告类任务不要使用口语化表达，优先使用正式、稳健、可汇报的句式。
```

### 查看 Skills 和统计

```Plain Text
/skills
/skill-stats
```

## 常用命令

### CLI 参数

|参数|功能|
|---|---|
|\-\-model, \-m|指定模型，覆盖 \.env 中的 MODEL|
|\-\-api\-base|覆盖 API base URL|
|\-\-plan|只读规划模式|
|\-\-accept\-edits|自动允许编辑类操作，推荐用于自动沉淀 Skills|
|\-\-yolo, \-y|跳过确认|
|\-\-dont\-ask|自动拒绝需要确认的操作，适合 CI|
|\-\-resume|恢复最近会话|
|\-\-max\-cost|费用上限|
|\-\-max\-turns|最大 agentic turns|

### REPL 命令

|命令|功能|
|---|---|
|/clear|清空对话历史|
|/plan|切换 Plan Mode|
|/cost|显示 token 和费用估算|
|/compact|手动压缩上下文|
|/memory|列出长期记忆|
|/skills|列出可用 Skills|
|/skill\-stats|查看 Skill 使用和演化统计|
|/extract\_now \[hint\]|抽取当前 pending window|
|/skill\-feedback \<skill\> \<rating\> \[note\]|记录 Skill 反馈|
|/skill\-evolve \<skill\> \<lesson\>|手动演化 Skill|
|/skill\-create \<name\> \| \<description\> \| \<when\-to\-use\> \| \<instructions\>|手动创建 Skill|

## Skills 是什么

Skill 是一个可复用能力说明文件，通常是一个带 frontmatter 的 [SKILL\.md](http://SKILL.md)。它保存的不是某次任务的具体内容，而是未来同类任务可复用的方法、规范、偏好或流程。

Skill 路径：

```Plain Text
用户级：~/.bear/skills/<skill_name>/SKILL.md
项目级：<project>/.bear/skills/<skill_name>/SKILL.md
```

示例：

```Plain Text
---
name: code_review
description: Review code changes with a bug-risk-first mindset.
when-to-use: When the user asks for code review.
user-invocable: true
context: inline
---

# Workflow

1. Read the relevant code first.
2. Lead with bugs, regressions, security risks, and missing tests.
3. Cite file paths and line numbers when possible.
4. Keep summary secondary to findings.
```

Skill 和 Memory 的区别：

|类型|保存内容|
|---|---|
|Memory|用户偏好、项目事实、历史决策、参考资料|
|Skill|可复用任务流程、输出规范、领域方法|

## MCP 支持

Bear Code 支持 MCP 外部工具扩展。MCP Server 可以通过 stdio JSON\-RPC 暴露工具，Bear Code 会将其包装为 Agent 可调用工具。

配置来源：

```Plain Text
~/.bear/settings.json
<project>/.bear/settings.json
<project>/.mcp.json
```

配置示例：

```Plain Text
{
  "mcpServers": {
    "example": {
      "command": "python",
      "args": ["server.py"],
      "env": {}
    }
  }
}
```

工具命名规则：

```Plain Text
mcp__<serverName>__<toolName>
```

每个 MCP 请求默认超时为 60 秒，可在对应服务器配置中设置 `"requestTimeout": 120`（单位：秒）。初始化和工具发现仍各限 15 秒。断线、超时及取消会清理等待中的请求；可能有副作用的工具调用不会自动重试。

## 权限与回归检查

Plan Mode 允许内置只读工具和受同样限制的 Skill/子 Agent；只有当前计划文件可以写入。`allow` 规则不能绕过 Plan Mode，退出 Plan Mode 必须有审批回调确认，一次性 `--plan` 运行不会自行切换为执行模式。

子 Agent 和 fork Skill 继承父 Agent 的权限、确认回调、模型凭据以及剩余预算。默认模式和 `--accept-edits` 下，Shell、未显式允许的 MCP 工具，以及工作目录外的文件或 Skill 修改需要确认；`--dont-ask` 自动拒绝这些确认操作。显式 `allow` 规则可授权相应操作，`--yolo` 则按其含义跳过权限确认。

文件写入的目录检查会解析 `..` 和符号链接，绝对路径不会被静默映射到项目中的同名文件。这是应用层权限控制；内置读取工具仍可读取工作目录外的文件，获准运行的 Shell/MCP 也具有本机进程权限。Dockerfile 提供容器运行方式，项目尚未实现操作系统级沙箱。

回归测试使用 Python 标准库 `unittest`，模型响应由模拟对象提供，MCP 使用临时测试子进程，不需要真实 key 或 API 额度：

```bash
python -m unittest discover -s tests -v
```

测试覆盖权限规则、目录与符号链接、工具恰好执行一次、两种模型协议、Plan 审批、子 Agent 继承、MCP 超时/断线/取消、Shell 取消、压缩及会话原子保存。

## Docker 运行

构建镜像：

```Plain Text
docker build -t bear-code .
```

启动交互式会话：

```Plain Text
docker run --rm -it \
  --env-file .env \
  -v "$PWD:/workspace" \
  -v bear-code-sessions:/root/.bear-code \
  -v bear-code-memory:/root/.BearCode \
  bear-code
```

允许自动沉淀 Skills：

```Plain Text
docker run --rm -it \
  --env-file .env \
  -e BEAR_AUTO_SKILL_EVOLUTION=1 \
  -e BEAR_AUTO_SKILL_TARGET=project \
  -v "$PWD:/workspace" \
  -v bear-code-sessions:/root/.bear-code \
  -v bear-code-memory:/root/.BearCode \
  bear-code --accept-edits
```

## 重要数据路径

|数据|路径|
|---|---|
|项目级 Skills|\.bear/skills/\<skill\_name\>/SKILL\.md|
|用户级 Skills|\~/\.bear/skills/\<skill\_name\>/SKILL\.md|
|Skills 自进化审计|\.bear/skill\-evolution/|
|长期记忆|\~/\.BearCode/projects/\<project\_hash\>/memory/|
|会话历史|\~/\.bear\-code/sessions/|
|大工具结果|\~/\.bear\-code/tool\-results/|
|Plan Mode 计划|\~/\.bear/plans/|

## 适合如何使用

Bear Code 适合：

- 学习 Claude Code 类工具的 Agent Loop 和工具调用机制。

- 学习如何做本地文件编辑型 Agent 的权限控制。

- 学习 Skills、Memory、MCP、子 Agent 如何接入同一个 Runtime。

- 扩展成个人 Coding Agent。

- 扩展成带长期记忆和可复用经验沉淀的领域 Agent。

如果只看一个核心点：Bear Code 是一个会把稳定用户反馈沉淀成 Skills 的 **自进化 Harness Agent**。
