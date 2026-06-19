# `hindcast/` — v0.5 MVP 代码包

> 🎯 从 `prototype-w3-hard-gate/` 提升而来的**真实代码**（非 throwaway）。
> 📌 设计决策：纯多数投票，无 RA-CR 辩论（见 [`09-ADR-PURE-VOTING-MVP.md`](../09-ADR-PURE-VOTING-MVP.md)）。
> 📅 状态：v0.5 MVP scaffold（2026-05-13）

---

## 安装

```bash
cd ~/Desktop/Hindcast-鉴往/hindcast
pip install -e ".[dev]"
```

## 用法

```bash
# 单时点常态预测
hindcast predict 2022-02-23

# 8 时点全样本回测
hindcast backtest

# 单时点回测
hindcast backtest --only 2008

# 启动 Web UI（默认 127.0.0.1:8000）
hindcast web --port 8765
```

环境变量：
- `OPENAI_API_KEY` — 必须
- `OPENAI_BASE_URL` — 默认 `https://sz.uyilink.com/v1`
- `HINDCAST_MODEL` — 默认 `gpt-5.4-mini`

---

## 接入 Claude Desktop / Cursor / Claude Code（MCP）

Hindcast 是一个 MCP server——任何 MCP 客户端都能调它的 3 个 tool：

| Tool | 用途 | 成本 |
|---|---|---|
| `list_snapshots` | 列出 4 个历史时点 | 0 |
| `get_structural_state(date)` | 拿某日的 15 变量结构状态 | 0 |
| `predict_steady_state(date)` | 跑 4 学派常态预测 + 投票 | ~$0.02 / 30-60s |

### Claude Desktop 配置

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "hindcast": {
      "command": "/Users/a26976/Desktop/Hindcast-鉴往/hindcast/.venv/bin/hindcast-mcp",
      "env": {
        "OPENAI_API_KEY": "sk-...",
        "OPENAI_BASE_URL": "https://sz.uyilink.com/v1",
        "HINDCAST_MODEL": "gpt-5.4-mini"
      }
    }
  }
}
```

重启 Claude Desktop → 工具栏会出现 🔌 hindcast。

### Cursor 配置

`~/.cursor/mcp.json` 或项目级 `.cursor/mcp.json`，结构同上。

### 用法示例（自然语言）

> "用 hindcast 看 2022 俄乌制裁那天的 4 学派常态预测"

Claude 会调 `predict_steady_state("2022-02-23")` 返回完整 verdict + 多数投票方向，然后用自然语言回答。

> "拉一下 2008 雷曼时点的 15 个结构变量"

调 `get_structural_state("2008-09-14")`。

### 自己跑（绕过 MCP 客户端）

```bash
hindcast-mcp                       # stdio 模式
# 或
python -m hindcast.mcp_server
```

可用 [@modelcontextprotocol/inspector](https://github.com/modelcontextprotocol/inspector) 调试：
```bash
npx @modelcontextprotocol/inspector hindcast-mcp
```

---

## 模块布局

```
src/hindcast/
├── state.py          14 结构变量定义 + StructuralState 类
├── schools.py        4 学派 system prompts（基于 01 §3.2.2 ⭐ 表）
├── agents.py         Agent.ask_school() → Verdict
├── predict.py        主公开 API: predict() → Forecast（4 学派并行 + 多数投票）
├── backtest.py       run_backtest() → BacktestReport
├── cli.py            argparse 入口
├── mcp_server.py     MCP server（hindcast-mcp 入口）
├── web.py            FastAPI 后端（hindcast web 启动）
├── llm.py            OpenAI client wrapper（含 retry + proxy 处理）
└── data/
    ├── snapshots.py     8 历史时点 15 变量
    └── ground_truth.py  8 时点真实金价路径

web/
└── index.html        Tailwind CDN + Alpine.js 单页 UI
```

## Web UI 用法

```bash
# 启动
hindcast web --port 8765
# 或
hindcast-mcp     # MCP 模式（Claude Desktop / Cursor）
```

浏览器打开 http://127.0.0.1:8765 →
1. 选历史时点（8 个）
2. 查看 15 变量当前状态
3. 点"让 4 学派跑预测"（~30-60s，$0.02）
4. 看 4 学派 verdict + 多数投票方向 + ground truth 比对（✅ HIT / ❌ MISS）

API docs: http://127.0.0.1:8765/docs

---

## 公开 API

```python
from hindcast import predict, StructuralState
from hindcast.data import SNAPSHOTS

forecast = predict(SNAPSHOTS["2022-02-23"])
print(forecast.horizons["T+5"].dir)        # "up"
print(forecast.is_unanimous)               # True / False
print(forecast.is_split)                   # True / False
```

后续将被 MCP server（C1, 07 Top #2）包装为 `predict_steady_state` tool。

---

## 不在 MVP 范围

- RA-CR 辩论协议（实测劣化，详见 09 ADR）
- MoE 加权
- CONTRADICTS 强制注入
- GraphRAG / CausalRAG 集成（另一终端在做）
- 事件修正层（v0.4 §3.3 W4 任务）
- 反事实沙盒（v0.4 §3.4 W7 任务）
- Web UI

这些都在 v0.5 后续 / v0.6 范围。

---

## 下一步

1. ✅ ~~`pip install -e .` + `hindcast backtest`~~（已验证）
2. ✅ ~~扩 snapshots 到 8 时点~~（已扩，N=8 实测 75% 命中率，T+5=87.5%/T+20=62.5%）
3. ✅ ~~MCP server~~（已落地，3 tool 烟测通过）
4. **接入 GraphRAG/CausalRAG**：等用户的另一终端跑完，改 `agents.ask_school()` 注入 retrieved evidence
5. **事件修正层 v0.4 §3.3**：T+20 仅 62.5% → 需要叠加事件后续动态补 long-horizon 命中率
6. **Web UI scaffold**（v0.4 §7）：Next.js + shadcn 包 `predict()` REST API
