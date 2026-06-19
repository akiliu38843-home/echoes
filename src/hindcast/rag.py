"""CausalRAG thin client — hindcast.agents 通过本模块拿 evidence。

CausalRAG 实际代码在 `04-graphrag-build/causal_rag/`（独立模块，可单独跑测试）。
这里通过 sys.path 注入引用，避免把 hindcast 跟 RAG 仓库耦合死。

启用方式：env `HINDCAST_USE_RAG=1` → ask_school() 自动注入 evidence。
RAG 失败时优雅降级到无 evidence 调用，不破坏 baseline 75%。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# ─── path injection ───
RAG_ROOT = Path("/Users/a26976/Desktop/Hindcast-鉴往/04-graphrag-build")
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))


_RETRIEVER_SINGLETON: Optional[Any] = None
_INIT_ERROR: Optional[str] = None


def is_enabled() -> bool:
    """Check if RAG should be used (env flag + module importable)."""
    if os.getenv("HINDCAST_USE_RAG", "0") != "1":
        return False
    return _get_retriever() is not None


DEFAULT_GRAPHRAG_ENDPOINT = "http://127.0.0.1:8001"


def _get_retriever():
    """Lazily build (and cache) the CausalRetriever singleton.

    若 GraphRAG endpoint (默认 :8001) 可达 → 启用 GraphRAGClient (D 路径完整)；
    否则降级到 offline 模式（只跑 DAG 路径枚举 + 约束）。
    """
    global _RETRIEVER_SINGLETON, _INIT_ERROR
    if _RETRIEVER_SINGLETON is not None:
        return _RETRIEVER_SINGLETON
    if _INIT_ERROR is not None:
        return None
    try:
        from causal_rag.retriever import CausalRetriever  # type: ignore
        from causal_rag.graphrag_client import GraphRAGClient  # type: ignore

        # 尝试探测 :8001 是否可用
        endpoint = os.getenv("GRAPHRAG_ENDPOINT", DEFAULT_GRAPHRAG_ENDPOINT)
        graphrag_client = None
        try:
            import requests
            r = requests.post(
                f"{endpoint}/query",
                json={"school": "austrian", "query": "ping"},
                timeout=5,
            )
            if r.status_code == 200:
                graphrag_client = GraphRAGClient(endpoint=endpoint)
                print(f"[hindcast.rag] GraphRAGClient connected: {endpoint}")
        except Exception as e:
            print(f"[hindcast.rag] GraphRAG offline at {endpoint}: {e}")

        _RETRIEVER_SINGLETON = CausalRetriever(graphrag=graphrag_client)
        return _RETRIEVER_SINGLETON
    except Exception as e:
        _INIT_ERROR = f"{type(e).__name__}: {e}"
        return None


def retrieve_evidence(
    school: str,
    structural_state: dict[str, float],
    horizon: str = "T+5",
    target_asset: str = "XAU/USD",
    target_direction: str = "up",
    mode: str = "steady_state",
) -> Optional[dict[str, Any]]:
    """跑一次 CausalRAG 5 步检索。

    Returns:
        dict — serialized CausalEvidence (supports/contradicts/top_signals/precedents)
              or None if RAG disabled / unavailable / failed.
    """
    retriever = _get_retriever()
    if retriever is None:
        return None

    try:
        from causal_rag.schemas import CausalQuery  # type: ignore
        query = CausalQuery(
            school=school,
            structural_state=structural_state,
            target_asset=target_asset,
            horizon=horizon,  # type: ignore[arg-type]
            mode=mode,  # type: ignore[arg-type]
            top_k=5,
        )
        evidence, _ = retriever.retrieve(query, target_direction=target_direction)
    except Exception as e:
        # RAG 失败 → 降级，不破 baseline
        return {"_failed": True, "_error": f"{type(e).__name__}: {e}"}

    # 序列化为 prompt 友好的 dict
    return {
        "supports": [_path_summary(p) for p in evidence.supports[:5]],
        "contradicts": [_path_summary(p) for p in evidence.contradicts[:3]],
        "structural_top_signals": evidence.structural_top_signals,
        "historical_precedents": evidence.historical_precedents,
        "is_counterfactual": evidence.is_counterfactual,
        "provenance": evidence.provenance,
    }


def _path_summary(path: Any) -> dict:
    """Compact serialization of a CausalPath (含 D 路径 text_excerpts)."""
    return {
        "nodes": list(path.nodes),
        "aggregate_sign": path.aggregate_sign,
        "school": path.school,
        "evidence_cases": list(path.evidence_cases or []),
        "cited_docs": list(getattr(path, "cited_docs", None) or [])[:3],
        "text_excerpts": list(getattr(path, "text_excerpts", None) or [])[:2],
    }


def format_evidence_for_prompt(evidence: dict[str, Any]) -> str:
    """把 evidence dict 渲染成给 LLM 的 markdown context。"""
    if not evidence or evidence.get("_failed"):
        return ""

    lines = ["", "---", "## 🧠 CausalRAG 检索到的因果证据"]
    lines.append("")
    lines.append("**你必须**: 在 verdict 的 `top_signals` 和 `historical_precedents` 字段")
    lines.append("**只能使用**以下 supports 中实际出现的 ID（不要自己想其他的）。")
    lines.append("")

    lines.append(f"### supports（你学派支持的因果链，按 score 排序）")
    for i, p in enumerate(evidence.get("supports", []), 1):
        nodes = " → ".join(p["nodes"])
        sign = p["aggregate_sign"]
        cases = p.get("evidence_cases", [])
        cases_str = f" [evidence: {', '.join(cases)}]" if cases else ""
        lines.append(f"  {i}. {nodes}  (aggregate {sign}){cases_str}")
        docs = p.get("cited_docs", [])
        if docs:
            lines.append(f"     📚 cited_docs: {', '.join(docs)}")
        excerpts = p.get("text_excerpts", [])
        if excerpts:
            for j, ex in enumerate(excerpts[:2], 1):
                lines.append(f"     💬 文献摘录 {j}: {ex[:300]}")

    lines.append("")
    lines.append(f"### contradicts（对手学派会用的反驳链——你要在 reasoning 里反击）")
    for i, p in enumerate(evidence.get("contradicts", []), 1):
        nodes = " → ".join(p["nodes"])
        lines.append(f"  {i}. ({p['school']}) {nodes}  (aggregate {p['aggregate_sign']})")

    lines.append("")
    lines.append(f"### 顶部结构信号 (use these as top_signals): {evidence.get('structural_top_signals', [])}")
    lines.append(f"### 历史先例 (use these as historical_precedents): {evidence.get('historical_precedents', [])}")
    lines.append("")
    return "\n".join(lines)


# ─── 叙事路径 RAG: 历史时期映射 (22-ADR §2) ──────────────────────────────────

_CASES_CACHE: Optional[list[dict]] = None


def load_history_cases() -> list[dict]:
    """Load the 12 historical structural snapshots (causal_rag/data/history_cases.json)."""
    global _CASES_CACHE
    if _CASES_CACHE is not None:
        return _CASES_CACHE
    path = RAG_ROOT / "causal_rag" / "data" / "history_cases.json"
    try:
        with open(path) as f:
            _CASES_CACHE = json.load(f)["cases"]
    except Exception:
        _CASES_CACHE = []
    return _CASES_CACHE


def retrieve_for_narrative(school: str, case_id: str) -> Optional[dict[str, Any]]:
    """Retrieve causal evidence using a historical case's structural snapshot.

    Reuses retrieve_evidence() — same CausalRAG pipeline, different structural_state source.
    """
    cases = load_history_cases()
    case = next((c for c in cases if c["id"] == case_id), None)
    if not case:
        return None
    return retrieve_evidence(
        school=school,
        structural_state=case["structural_snapshot"],
        horizon="T+5",
        target_asset="XAU/USD",
        target_direction="up",
    )


def format_evidence_for_narrative(evidence: dict[str, Any], case_label: str) -> str:
    """Narrative-friendly evidence injection — no directional mandate."""
    if not evidence or evidence.get("_failed"):
        return ""
    lines = [
        "",
        "---",
        f"## 📚 历史结构类比: {case_label}",
        "",
        "以下因果路径来自与本事件结构环境最相似的历史时期，供构建叙事框架参考。",
        "**注意**: 这是结构相似性匹配，不是方向预测——不要据此给出价格方向。",
        "",
    ]
    supports = evidence.get("supports", [])
    if supports:
        lines.append("### 你学派支持的机制路径")
        for i, p in enumerate(supports[:4], 1):
            nodes = " → ".join(p.get("nodes", []))
            cases_str = ""
            if p.get("evidence_cases"):
                cases_str = f" [{', '.join(p['evidence_cases'])}]"
            lines.append(f"  {i}. {nodes}{cases_str}")
            for ex in (p.get("text_excerpts") or [])[:1]:
                lines.append(f"     💬 {ex[:200]}")
    contradicts = evidence.get("contradicts", [])
    if contradicts:
        lines.append("")
        lines.append("### 对立学派路径")
        for i, p in enumerate(contradicts[:2], 1):
            nodes = " → ".join(p.get("nodes", []))
            lines.append(f"  {i}. ({p.get('school', '?')}) {nodes}")
    precedents = evidence.get("historical_precedents", [])
    if precedents:
        lines.append("")
        lines.append(f"### 历史先例 IDs: {precedents}")
    lines.append("")
    return "\n".join(lines)


def availability_report() -> dict:
    """Diagnostic helper — check if RAG can be loaded."""
    enabled = os.getenv("HINDCAST_USE_RAG", "0") == "1"
    r = _get_retriever()
    return {
        "env_flag_set": enabled,
        "retriever_loaded": r is not None,
        "init_error": _INIT_ERROR,
        "rag_root_exists": RAG_ROOT.exists(),
        "rag_root": str(RAG_ROOT),
    }
