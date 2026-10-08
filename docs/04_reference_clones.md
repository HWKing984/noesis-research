# 参考仓库台账（reference/）

> 2026-10-08 拉取。本文件是**已提交**的出处记录；`reference/` 目录本身**不进版本库**（`.gitignore:27`），与 NOESIS 仓库的 `参考/` 约定一致（见其 `THIRD_PARTY_NOTICES.md`）。

## 0 约定（照抄 NOESIS 已验证的做法）

1. **浅克隆**（`--depth 1 --single-branch --branch main --no-tags`），只取 tip 树，不拉历史。
2. **上游源码零修改**：4 个克隆的 `git status --porcelain` 均为 0 项。
3. **不提交**：`git check-ignore -v reference/deepagents` → `.gitignore:27:reference/`。
4. **出处可追**：每个克隆记录 upstream URL + 克隆到的 commit；移植/借用任何文件时，须在该文件头写明上游文件与行号范围（NOESIS 的 `THIRD_PARTY_NOTICES.md` 就是这个格式）。

## 1 出处台账

| 目录 | 上游 | 克隆到 commit | 远端 main 对照 | 许可 | 磁盘 |
|---|---|---|---|---|---|
| `reference/deepagents` | `github.com/langchain-ai/deepagents` | `caaa7e7c12d214afa5cf0a1afed8eb6232aa6f7b` | `caaa7e7c12d2` ✅ 一致 | MIT（Copyright LangChain, Inc.） | 84.8 MB |
| `reference/paper-qa` | `github.com/Future-House/paper-qa` | `57e89f7223b0960d5ee5ea048c69e3c47e088572` | `57e89f7223b0` ✅ 一致 | Apache-2.0 | 59.5 MB |
| `reference/neo4j-graphrag-python` | `github.com/neo4j/neo4j-graphrag-python` | `4e3d6dc737c21571a171e9805b2373c33b6d1582` | `4e3d6dc737c2` ✅ 一致 | **Apache-2.0**，部分文件为 **PSF-2.0**（`LICENSE.txt` 原文声明，源码内已逐处标注） | 6.5 MB |
| `reference/agent-chat-ui` | `github.com/langchain-ai/agent-chat-ui` | `28cfb43a62b7179ed4065dd761e16ece8c29d983` | `28cfb43a62b7` ✅ 一致 | MIT（Copyright Brace Sproul） | 0.7 MB |

**说明**：`neo4j-graphrag-python` 在 GitHub API 上报告为 `NOASSERTION`（许可文件叫 `LICENSE.txt`，GitHub 无法归类）。实际拉取原文确认是 Apache-2.0 + PSF-2.0 混合，**不是**"未知许可"，也没有 GNU / BUSL 条款。这条是按原文核实的，不是凭印象。

## 2 各仓库「看什么」+ 已核实结论

### 2.1 `deepagents` —— T4 的执行底座

- `libs/deepagents/pyproject.toml` 实测：`name = "deepagents"`、**`version = "0.7.23"`**、`requires-python = ">=3.11,<4.0"`、MIT。依赖与 PyPI 元数据逐条一致：`langchain>=1.4.3,<2.0.0`、`langchain-core>=1.6.7,<2.0.0`、`langchain-anthropic>=1.7.5,<2.0.0`、`langchain-google-genai>=4.4.0,<5.0.0`、`langsmith`、`packaging`、`wcmatch`。
  → **`services/research-agent/requirements.txt` 里 `deepagents==0.7.23` 的 pin 由「PyPI 元数据 + 克隆源码」两处独立对上。**
- 这是个 **monorepo**，不止一个包：`libs/deepagents`（核心）、`libs/code`、`libs/acp`、`libs/evals`、`libs/talon`、`libs/partners/{daytona,modal,quickjs,runloop,vercel}`、`examples/*`。
  → 装 `deepagents` 只会拿到核心包；`libs/partners/*` 都是可选扩展，不装。
- **`examples/deep_research/` 是本项目最贴近的参考实现**（深度研究型 Agent 的搭法）。虽然是示例、不保证 API 稳定，但结构可直接对照 T4。
- 构建后端是 setuptools（非 uv），`requires-python >=3.11`。

### 2.2 `paper-qa` —— T6 的论文内容引擎，且**顺带解决 T8**

- `src/paperqa/clients/` 实测含：**`openalex.py`、`crossref.py`、`semantic_scholar.py`**、`unpaywall.py`、`retractions.py`。
  → 计划 T8 原本要自己写的三个外部连接器，**上游已经有功能实现**（`httpx` + `tenacity` 重试、`DOIOrTitleBasedProvider` 抽象、`DOIQuery`/`TitleAuthorQuery`、`OPENALEX_MAILTO` 环境变量、`DOINotFoundError`）。这是评审"能直接复用就直接复用"原则的直接落点：**优先复用，不重写**。
  → 但**身份合并政策仍归本项目**：上游用 `strings_similarity` 做标题相似度匹配；本项目规则是「仅标题相似度匹配一律留为待确认候选，**不得合并论文身份**」。复用其网络层与解析，判定层按我们的规则收紧。
- `src/paperqa/agents/`（`main.py` / `search.py` / `tools.py` / `env.py`）、`core.py`、`docs.py`、`llms.py`、`prompts.py`、`configs/tier1..tier5_limits.json` + `fast/high_quality/...` 预设。
- `packages/` 是插件 monorepo（`paper-qa-pypdf` / `paper-qa-pymupdf` / `paper-qa-docling` / `paper-qa-nemotron`），解析器与之解耦。
- 版本在 `pyproject.toml` 里是动态生成；PyPI 最新发布为 `2026.8.12`，本次克隆的是 main tip。

### 2.3 `neo4j-graphrag-python` —— 图谱检索器参考

- `src/neo4j_graphrag/retrievers/` 实测含 **`vector.py` / `text2cypher.py` / `hybrid.py`**，另有 `tools_retriever.py`。
  → 计划 §10.5 推荐的「Vector / Text2Cypher / Hybrid 检索器」**核实存在**。
  → 计划同时写明：`Text2CypherRetriever` 生成的 Cypher **必须白名单校验**（只读 + 必带 `graphId` 过滤），否则会绕过现有全部参数边界。
- 许可：多数文件 Apache-2.0，部分文件 PSF-2.0（源码内逐处标注）。

### 2.4 `agent-chat-ui` —— 交互设计参考，**不是移植来源**

- 技术栈实测：**Next.js 16 + React 19 + Tailwind 4 + `@langchain/langgraph-sdk` + `langgraph-nextjs-api-passthrough`**，带 Next App Router 的 `src/app/api/[..._path]` BFF 转发层。
- 本工程前端将复用 **NOESIS 体系：Vite 5 + React 18 + Tailwind 4**。
- **结论：栈不匹配（Next App Router + React 19 ↔ Vite + React 18），组件不能直接搬。** 因此评审说的"优先原组件移植"，**移植对象应是 NOESIS 自身的组件**（`AgentPanel` / `AgentSwimlane` / `AnswerSummary` / `ArtifactPanel` / `GraphPanel` 等，同一栈），本仓库只提供信息层级与交互流程的参考：`src/components/thread/`（`index.tsx`、`messages/`、`history/`、`artifact.tsx`、`markdown-text.tsx`、`ContentBlocksPreview.tsx`）、`src/providers/{Stream,Thread,client}.tsx`、`src/lib/{ensure-tool-responses,agent-inbox-interrupt}.ts`。

## 3 归属要求（借用任何一行上游代码前必读）

| 上游 | 许可 | 要求 |
|---|---|---|
| deepagents | MIT | 保留版权与许可声明 |
| paper-qa | Apache-2.0 | 保留 NOTICE 与版权声明；改动文件需标注 |
| neo4j-graphrag-python | Apache-2.0 + PSF-2.0 | 逐文件看标注；PSF 文件按 PSF 条款保留 |
| agent-chat-ui | MIT | 保留版权与许可声明 |

本项目已有一处同样的实践可照抄：NOESIS 的 `THIRD_PARTY_NOTICES.md` 用「上游文件 + 行号范围」记录每个算法移植（如 `citation_trace/verify.py` ← openjiuwen `citation_verify_research.py:65-115`）。新工程借用上游代码时，同样在该文件头写明来源与行号。

## 4 重新拉取 / 复现

```powershell
# 关键：本机必须走 Clash 代理，且 schannel TLS 后端会握手失败 —— 显式换 openssl
$px = "http://127.0.0.1:7890"
$common = @("-c","http.proxy=$px","-c","https.proxy=$px","-c","http.sslBackend=openssl",
            "-c","http.lowSpeedLimit=1000","-c","http.lowSpeedTime=30")

git @common clone --depth 1 --single-branch --branch main --no-tags `
    https://github.com/langchain-ai/deepagents.git reference/deepagents
```

**本机两个坑（已实测）：**

1. **`schannel` TLS 后端走该代理会握手失败**：报 `schannel: failed to receive handshake, SSL/TLS connection failed`，且失败后进程会长时间挂住不返回。加 `-c http.sslBackend=openssl` 后 4/4 全部成功。
2. **克隆前必须确认目标目录不存在或为空**：被中断的克隆会留下半成品目录，`git clone` 直接报 `destination path ... already exists and is not an empty directory`。另外在被中断的残留目录里跑 `git -C <dir> rev-parse HEAD` 会**向上找到父仓库**并返回父仓库的 sha —— 那是个假读数，别信。

## 5 未处理项：NOESIS 本地工作树与远端已分歧

`D:\a-Soft` 是 NOESIS 的实际工作树，本次**只做只读比对，未做任何 fetch / pull / checkout**：

| 项 | 值 |
|---|---|
| 本地 HEAD | `5efbadd085240bfcb8874f960a19c063bc65110d` |
| 本地分支 | `codex/system-audit-repairs-20260930` |
| 本地未提交改动 | **306 项** |
| 远端同名分支 | `b97305e4ddd8c4b533e4b5c3c90bce9b53e5011b`（与本地 HEAD **不同**） |
| 远端其他分支 | `master` = `82e2180`、`model` = `f971e8e` |
| 远端 | `HWKing984/An-Adaptive-Learning-System-Driven-by-Learner-State-Modeling-and-Dynamic-Decision-Making` |

**没有自动同步的理由**：工作树带 306 项未提交改动，任何 `pull` / `reset` / `checkout` 都可能覆盖他正在做的活。移植用的 NOESIS 源码以**本地工作树**为准（比 5efbadd 更新）；远端那份是历史提交。

同步这件事需要他决定，因为只有他知道那 306 项是什么状态。
