"""MCP server——把 hindcast.predict() 暴露成 MCP tool。

供 Claude Desktop / Cursor / Claude Code 用户在客户端配置后直接调用：
  Claude Code 里："对 2022 俄乌制裁跑一下 4 学派常态预测"
  → 调 predict_steady_state("2022-02-23")
  → 返回 4 学派 verdict + 多数投票方向

启动：
  hindcast-mcp                       # stdio 模式（被 Claude Desktop 等启动）
  python -m hindcast.mcp_server      # 同上

配置示例见 hindcast/README.md "接入 Claude Desktop / Cursor" 段。
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from hindcast.data import GROUND_TRUTH, SNAPSHOTS
from hindcast.predict import predict
from hindcast.state import VARIABLES


mcp = FastMCP("hindcast")


@mcp.tool()
def list_snapshots() -> list[dict[str, str]]:
    """列出所有可用的历史结构状态快照。

    返回每个快照的日期、标签、事件简介——客户端拿到后可让用户挑选哪个时点跑预测。
    """
    return [
        {
            "as_of": snap.as_of,
            "label": snap.label,
            "event": GROUND_TRUTH.get(snap.as_of, {}).get("event", ""),
        }
        for snap in SNAPSHOTS.values()
    ]


@mcp.tool()
def get_structural_state(date: str) -> dict[str, Any]:
    """获取指定日期的 14/15 结构状态变量快照。

    参数 date: ISO 日期，如 "2022-02-23"。可用日期见 list_snapshots()。

    返回：变量 ID → {名称, 值, 各学派关注度⭐}
    """
    snap = SNAPSHOTS.get(date)
    if not snap:
        return {
            "error": f"No snapshot for {date}",
            "available_dates": list(SNAPSHOTS.keys()),
        }
    return {
        "as_of": snap.as_of,
        "label": snap.label,
        "variables": {
            var_id: {
                "name": var.name,
                "value": snap.values.get(var_id),
                "school_relevance": var.school_relevance,
            }
            for var_id, var in VARIABLES.items()
        },
    }


@mcp.tool()
def predict_steady_state(date: str) -> dict[str, Any]:
    """跑 4 学派常态预测（v0.5 MVP：纯多数投票，无 RA-CR 辩论）。

    输入 date: 必须是 list_snapshots() 里的日期之一。

    返回：
      - asset: "XAU/USD"
      - horizons: 每个时间维度的整合方向 + 4 学派票数 + 各学派意见
      - verdicts: 4 个学派的详细 verdict（top_signals / 历史先例 / reasoning / confidence）
      - is_unanimous: 是否 4 学派一致
      - is_split: 是否出现 2:2 平局

    Note: 此调用会触发 4 次 LLM 调用，约 30-60 秒，约消耗 $0.02。
    """
    snap = SNAPSHOTS.get(date)
    if not snap:
        return {
            "error": f"No snapshot for {date}",
            "available_dates": list(SNAPSHOTS.keys()),
        }

    forecast = predict(snap)
    return {
        "as_of": forecast.as_of,
        "label": forecast.label,
        "asset": forecast.asset,
        "n_valid_schools": forecast.n_valid_schools,
        "is_unanimous": forecast.is_unanimous,
        "is_split": forecast.is_split,
        "horizons": {
            h: {
                "direction": hf.dir,
                "vote_counts": hf.vote_counts,
                "school_directions": hf.school_directions,
            }
            for h, hf in forecast.horizons.items()
        },
        "verdicts": [
            {
                "school": v.school,
                "verdict": {
                    h: {"dir": hz.dir, "range_pct": hz.range_pct}
                    for h, hz in v.verdict.items()
                },
                "top_signals": v.top_signals,
                "historical_precedents": v.historical_precedents,
                "reasoning": v.reasoning,
                "confidence": v.confidence,
                "failed": v._failed,
            }
            for v in forecast.verdicts
        ],
    }


def main():
    """Entry point for `hindcast-mcp` console script."""
    mcp.run()


if __name__ == "__main__":
    main()
