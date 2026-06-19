"""货币政策利率预测（Phase 1 新增）。

预测下次 FOMC 决议的方向 + 幅度：
  action: hike / cut / hold
  bps: 0 / 25 / 50 / 75 / 100

学派立场（hardcoded prior，注入 prompt）：
  Austrian:       鹰派，通胀容忍度低，恒倾向 hike 或 hold-tight
  Monetarist:     Taylor Rule 机械执行者
  Keynesian:      关注失业 + 总需求，偏鸽派
  Rational Exp:   看 Fed funds futures market priced-in + forward guidance
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal, Optional

from openai import OpenAI
from pydantic import BaseModel, Field

from hindcast.llm import chat_json
from hindcast.state import SCHOOLS, School, StructuralState


Action = Literal["hike", "cut", "hold"]
ActionAggregate = Literal["hike", "cut", "hold", "NO_SIGNAL"]


SCHOOL_MONETARY_STANCE = {
    "austrian": """**🦘 你的货币政策立场（恒定先验）**：
- 鹰派（hawkish）极度强烈——通胀是货币现象，容忍度极低
- 你恒倾向 **hike 或 hold-tight**；只在严重衰退 + 通胀 ≤ 1% 时才接受 cut
- 你恒批评 Fed "behind the curve"
- 你看 Taylor Rule 但加 1% buffer（你认为 r* 应该高于 2%）
""",
    "monetarist": """**📊 你的货币政策立场（恒定先验）**：
- **Taylor Rule 机械执行者**——你的 verdict 应该几乎等于 Taylor implied rate
- 你的决策框架：若 Taylor implied > current + 0.5% → hike (25-75bps)
              若 Taylor implied < current - 0.5% → cut
              否则 → hold
- 你引用 Friedman: "通胀是货币现象, 必须以规则锚定不靠自由裁量"
- 你反驳奥地利："QE 后没恶性通胀，所以 r* 不需高于 2%"
""",
    "keynesian": """**🏛️ 你的货币政策立场（恒定先验）**：
- 鸽派（dovish）——失业上行时主张 cut，财政 + 货币应协同
- 你看 unemployment gap 大于 inflation gap
- 当 u > u* + 0.5% → cut；u < u* - 0.5% 且通胀低 → hold
- 你引用 Krugman / Minsky / Kelton：长期低利率 + 主动财政是健康框架
""",
    "rational_expectations": """**🧮 你的货币政策立场（恒定先验）**：
- 看 **市场已经 priced-in 什么** —— Fed funds futures + forward guidance + dot plot
- 若 Fed 公开 forward guidance 已暗示 hike → 你跟着 hike
- 若市场 priced-in cut 但 Fed 没暗示 → 你说 hold（不能背叛 forward guidance）
- 你反驳奥地利："如果 priced-in 100% hike, hike 本身没冲击"
""",
}


POLICY_RATE_OUTPUT_FORMAT = """

---
## 🧬 深度识别模式（修 3 个系统性失败 case）

### Pattern 1: 政治压力 dominant（修 1971 Nixon）
当 **B1 CBI ≤ 7.0** AND **policy_event_imminent=True** AND headlines 提政治施压（选举年 / 总统公开施压）→ Fed **可能 cut 而非 hike**（即使 Taylor 说 hike）。
1971 Burns 在 Nixon 选举压力下背离 Taylor 转鸽是经典 case。

### Pattern 2: 微弱信号 → favor hold（修 1992 ERM）
当 **|Taylor deviation| < 0.5 pp** AND **|unemployment gap| < 0.5 pp** → 倾向 **hold** + confidence ≤ 0.4。
不要在弱信号上下注大幅 hike/cut。

### Pattern 3: 危机紧急降息识别（修 2008 Lehman）
当 event_window 含 "financial_crisis" / "Lehman" / "systemic_risk" 类标题 + GDP 已转负 → Fed **大概率紧急 cut ≥50 bps**，不管 Taylor 说什么。

---
## 输出 schema (严格 JSON)

{
  "school": "<your_school>",
  "action": "hike | cut | hold",
  "bps": <0 | 25 | 50 | 75 | 100>,         // hold 时 bps=0
  "next_fomc_horizon_days": <int>,           // 距离下次 FOMC 大约多少天（你估计）
  "top_signals": ["taylor_deviation", "unemployment_gap", "inflation_gap", ...],
  "taylor_implied_anchor": <float>,          // 你估算的 Taylor implied rate（可对比 current）
  "volatility_class": "exogenous_shock | endogenous_technical | stochastic_noise | structural_break",
  "attribution_note": "<1 句: 你的决策依据，必须显式提及 Taylor implied 与 current 的关系>",
  "reasoning": "<2-3 句解释你的立场如何映射到这次的决策>",
  "confidence": <0.0-1.0>
}

confidence 上限受 volatility_class 约束（同 ADR-002）：
- exogenous_shock ≤ 1.0
- endogenous_technical ≤ 0.3
- stochastic_noise ≤ 0.1
- structural_break ≤ 0.2

不要输出 JSON 以外的任何文字。
"""


class PolicyRateVerdict(BaseModel):
    school: School
    action: Action
    bps: int = 0
    next_fomc_horizon_days: int | None = None
    top_signals: list[str] = Field(default_factory=list)
    taylor_implied_anchor: float | None = None
    volatility_class: str = "exogenous_shock"
    attribution_note: str = ""
    reasoning: str = ""
    confidence: float = 0.0
    _failed: bool = False
    _error: Optional[str] = None


class PolicyRateForecast(BaseModel):
    as_of: str
    label: str
    target: str = "FED_FUNDS_RATE"
    current_fed_funds: float | None = None
    taylor_implied: float | None = None
    aggregate_action: ActionAggregate
    aggregate_bps: float                          # 平均 bps（如 25 / 37.5 等）
    vote_counts: dict[str, int]                   # {hike: 2, hold: 1, cut: 1}
    verdicts: list[PolicyRateVerdict]
    n_valid: int

    @property
    def is_unanimous(self) -> bool:
        return len(set(v.action for v in self.verdicts if not v._failed)) == 1

    @property
    def is_split(self) -> bool:
        actions = [v.action for v in self.verdicts if not v._failed]
        if not actions:
            return False
        c = Counter(actions)
        return max(c.values()) == 2 and sum(c.values()) == 4


def _build_user_prompt(state: StructuralState) -> str:
    base = state.format_for_prompt()
    base += "\n\n---\n\n"
    base += "**预测目标：美联储下次 FOMC 决议（hike / cut / hold + bps）**"
    if state.macro is None:
        base += "\n\n⚠️ 警告：本时点缺 macro 数据，你只能用 attribution_note 标注降级为 stochastic_noise + confidence ≤ 0.1。"
    return base


def _build_system_prompt(school: School) -> str:
    """学派身份 + 货币政策立场 + 输出格式。"""
    return SCHOOL_MONETARY_STANCE[school] + POLICY_RATE_OUTPUT_FORMAT


def ask_school_policy_rate(
    client: OpenAI, school: School, state: StructuralState
) -> PolicyRateVerdict:
    system_prompt = _build_system_prompt(school)
    user_prompt = _build_user_prompt(state)

    # Optional: 注入 CausalRAG evidence（HINDCAST_USE_RAG=1）——镜像 fx.ask_school_fx。
    # DAG 节点名为 FED_FUNDS（非本文件 target 的 FED_FUNDS_RATE）。RAG 失败优雅降级。
    from hindcast import rag
    if rag.is_enabled():
        evidence = rag.retrieve_evidence(
            school=school,
            structural_state=state.values,
            horizon="T+5",
            target_asset="FED_FUNDS",
        )
        if evidence and not evidence.get("_failed"):
            user_prompt += rag.format_evidence_for_prompt(evidence)

    raw = chat_json(client, system_prompt, user_prompt)
    if raw.get("_failed"):
        return PolicyRateVerdict(
            school=school, action="hold", bps=0,
            _failed=True, _error=raw.get("_error"),
        )

    action = raw.get("action", "hold")
    if action not in ("hike", "cut", "hold"):
        action = "hold"
    bps = int(raw.get("bps", 0))
    if action == "hold":
        bps = 0

    vc = raw.get("volatility_class", "exogenous_shock")
    confidence = float(raw.get("confidence", 0.5))
    caps = {"exogenous_shock": 1.0, "endogenous_technical": 0.3,
            "stochastic_noise": 0.1, "structural_break": 0.2}
    confidence = min(confidence, caps.get(vc, 1.0))

    return PolicyRateVerdict(
        school=school,
        action=action,
        bps=bps,
        next_fomc_horizon_days=raw.get("next_fomc_horizon_days"),
        top_signals=raw.get("top_signals", []),
        taylor_implied_anchor=raw.get("taylor_implied_anchor"),
        volatility_class=vc,
        attribution_note=raw.get("attribution_note", ""),
        reasoning=raw.get("reasoning", ""),
        confidence=confidence,
    )


def aggregate_action(verdicts: list[PolicyRateVerdict]) -> tuple[ActionAggregate, dict[str, int], float]:
    """多数投票 + 平均 bps（含方向符号：hike +bps, cut -bps, hold 0）。"""
    valid = [v for v in verdicts if not v._failed]
    if not valid:
        return "NO_SIGNAL", {}, 0.0
    counter = Counter(v.action for v in valid)
    # 平局优先：hold > cut > hike（最稳）
    sorted_actions = sorted(
        counter.most_common(),
        key=lambda x: (-x[1], {"hold": 0, "cut": 1, "hike": 2}[x[0]]),
    )
    winner = sorted_actions[0][0]
    signed_bps = sum(
        (v.bps if v.action == "hike" else -v.bps if v.action == "cut" else 0)
        for v in valid
    ) / len(valid)
    return winner, dict(counter), signed_bps


def run_policy_rate_backtest(snapshots=None):
    """跑 Fed funds 历史回测——对每个 snapshot 跑 predict_policy_rate, 对照 ground truth."""
    from hindcast.data import POLICY_RATE_GROUND_TRUTH, ALL_SNAPSHOTS
    snapshots = snapshots or [s for s in ALL_SNAPSHOTS if s.macro is not None]
    results = []
    for snap in snapshots:
        print(f"\n========== {snap.label} ({snap.as_of}) ==========")
        if snap.macro:
            implied = snap.macro.compute_taylor_implied()
            print(f"  current={snap.macro.current_fed_funds_target}%, taylor_implied={implied:.2f}%")
        forecast = predict_policy_rate(snap)
        for v in forecast.verdicts:
            if v._failed:
                print(f"  {v.school:<25} FAILED — {v._error}")
            else:
                print(f"  {v.school:<25} {v.action:>5} {v.bps:>4} bps  (conf {v.confidence:.2f})")
        gt = POLICY_RATE_GROUND_TRUTH.get(snap.as_of, {})
        hit_dir = (forecast.aggregate_action == gt.get("action"))
        results.append({
            "as_of": snap.as_of, "label": snap.label, "forecast": forecast,
            "gt": gt, "hit_dir": hit_dir,
        })
    # 打印总结
    print("\n\n========== Fed Funds Rate 命中率 ==========")
    print(f"{'时点':<32} {'pred':<6} {'pred bps':<10} {'GT':<6} {'GT bps':<8} {'hit'}")
    print("-" * 88)
    hits = 0
    total = 0
    for r in results:
        if not r["gt"]:
            print(f"{r['label']:<32} {r['forecast'].aggregate_action:<6} (no GT)")
            continue
        total += 1
        if r["hit_dir"]: hits += 1
        mark = "✅" if r["hit_dir"] else "❌"
        print(f"{r['label']:<32} {r['forecast'].aggregate_action:<6} {r['forecast'].aggregate_bps:+.0f} bps  "
              f"{r['gt']['action']:<6} {r['gt']['bps']:+}    {mark}")
    print("-" * 88)
    if total:
        print(f"方向命中率: {hits}/{total} = {hits/total*100:.0f}%")
        print(f"W3 hard gate: ≥ 60%  →  {'✅ PASS' if hits/total >= 0.6 else '❌ FAIL'}")
    return results


def predict_policy_rate(
    state: StructuralState,
    client: OpenAI | None = None,
) -> PolicyRateForecast:
    """4 学派对下次 FOMC 决议投票预测。"""
    from hindcast.llm import get_client
    client = client or get_client()

    verdicts: list[PolicyRateVerdict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(ask_school_policy_rate, client, school, state): school
            for school in SCHOOLS
        }
        for fut in as_completed(futures):
            verdicts.append(fut.result())

    winner, counts, avg_bps = aggregate_action(verdicts)
    n_valid = sum(1 for v in verdicts if not v._failed)

    macro = state.macro
    return PolicyRateForecast(
        as_of=state.as_of,
        label=state.label,
        current_fed_funds=macro.current_fed_funds_target if macro else None,
        taylor_implied=(macro.compute_taylor_implied() if macro else None),
        aggregate_action=winner,
        aggregate_bps=avg_bps,
        vote_counts=counts,
        verdicts=verdicts,
        n_valid=n_valid,
    )
