"""桥梁变量预测（v0.5.4 Phase 2.5）——服务于 XAU 集成预测。

预测 3 个 XAU 直接驱动变量：
  US_10Y_TIPS   实际收益率（gold #1 inverse driver）
  US_10Y_BEI    10Y 通胀预期（gold inflation hedge driver）
  DXY           美元综合指数（gold USD 计价 inverse driver）

XAU 经典定价分解:
  XAU/USD = -TIPS × β1 + BEI × β2 + (-DXY) × β3 + GPR × β4 + 央行购金 × β5

这 3 个 target 预测好后, XAU 变成"集成预测"——前面已预测的方向作为 prior。

4 学派对这 3 个 target 的立场:

US 10Y TIPS（实际收益率）:
  Austrian:    Fed "金融抑制"压低 → TIPS 长期偏低; 紧缩周期 TIPS 升
  Monetarist:  TIPS = nominal - inflation expectation, 机械
  Keynesian:   危机期 TIPS 急跌（flight + Fed cut）
  Rational Exp: 市场 priced-in 通胀路径

US 10Y BEI（通胀预期）:
  Austrian:    法币贬值 + QE → BEI 升
  Monetarist:  M2 增速 + 油价传导 → BEI
  Keynesian:   失业 + 劳动力市场 → BEI
  Rational Exp: 5Y5Y forward 已 priced-in

DXY（美元综合指数）:
  Austrian:    USD 法币长期看贬 (CBI + 财政恶化) → DXY 长期下行
  Monetarist:  Taylor differential (US vs G6) → DXY 同向
  Keynesian:   贸易余额 + 经常项 → DXY (US 逆差 → DXY 偏弱)
  Rational Exp: 市场已 priced-in 利差路径
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal, Optional

from openai import OpenAI
from pydantic import BaseModel, Field

from hindcast.agents import Direction
from hindcast.llm import chat_json
from hindcast.state import SCHOOLS, School, StructuralState


BridgeTarget = Literal["US_10Y_TIPS", "US_10Y_BEI", "DXY"]


SCHOOL_BRIDGE_STANCE = {
    "US_10Y_TIPS": {
        "austrian":              "Fed 金融抑制压低 TIPS, 但紧缩周期 + 财政恶化 → TIPS 应升",
        "monetarist":            "TIPS = nominal - inflation expectation 机械; 通胀升而 nominal 不升 → TIPS 跌",
        "keynesian":             "危机期 TIPS 急跌（flight to safety + Fed cut 预期）",
        "rational_expectations": "TIPS 市场已 priced-in 通胀路径; 只有通胀 surprise 才动",
    },
    "US_10Y_BEI": {
        "austrian":              "法币贬值 + QE + 财政赤字 → BEI 长期升",
        "monetarist":            "M2 增速 + 油价传导 + 通胀粘性 → BEI 机械",
        "keynesian":             "失业 gap + 劳动力市场紧 → BEI 升",
        "rational_expectations": "5Y5Y forward 反映理性 BEI; Fed 公开 forward guidance 是核心",
    },
    "DXY": {
        "austrian":              "USD 法币长期看贬 (CBI 下行 + 财政恶化) → DXY 长期下行; 但比烂逻辑下可能短期反弹",
        "monetarist":            "Taylor differential (US vs G6 EUR/JPY/GBP) → DXY 同向; US 加息周期 → DXY 强",
        "keynesian":             "贸易余额 + 经常项 → US 逆差 → DXY 偏弱; 危机期 USD safe haven",
        "rational_expectations": "市场已 priced-in 利差路径; forward DXY = spot × (1 + r_diff)",
    },
}


# 共用输出格式（含 DEEP_PATTERNS 共识）
BRIDGE_OUTPUT_FORMAT = """

---
## 🧬 深度识别模式

### Pattern 1: 政治压力 → Fed 转鸽 → TIPS 跌 / DXY 跌
B1 CBI ≤ 7.0 + 选举年 → 全 USD 资产偏弱

### Pattern 2: priced-in 翻转
事件已发酵 30+ 日 → 原始 driver 被 priced-in, 次级 driver 主导

### Pattern 3: 微弱信号 → flat
|结构信号| < 阈值 + 无事件窗激活 → 倾向 flat, confidence ≤ 0.4

---
## 输出 schema (严格 JSON)

{
  "school": "<your_school>",
  "verdict": {
    "T+5":  {"dir": "up | down | flat", "range_bps": [low_bps, high_bps]},
    "T+20": {"dir": "up | down | flat", "range_bps": [low_bps, high_bps]}
  },
  "top_signals": ["taylor_implied", "nominal_yield", "M2_growth", ...],
  "volatility_class": "exogenous_shock | endogenous_technical | stochastic_noise | structural_break",
  "attribution_note": "<1 句方向依据>",
  "reasoning": "<2-3 句>",
  "confidence": <0.0-1.0>
}

注: range_bps for yield/BEI is in basis points; for DXY is in index points × 100 (5 = 0.05).
confidence 上限受 volatility_class 约束（ADR-002）。
不要输出 JSON 以外的任何文字。
"""


class BridgeHorizon(BaseModel):
    dir: Direction
    range_bps: list[float] = Field(default_factory=lambda: [0.0, 0.0])


class BridgeVerdict(BaseModel):
    school: School
    target: BridgeTarget
    verdict: dict[str, BridgeHorizon]
    top_signals: list[str] = Field(default_factory=list)
    volatility_class: str = "exogenous_shock"
    attribution_note: str = ""
    reasoning: str = ""
    confidence: float = 0.0
    _failed: bool = False
    _error: Optional[str] = None

    def direction(self, horizon: str) -> Direction:
        return self.verdict.get(horizon, BridgeHorizon(dir="flat")).dir


class BridgeHorizonForecast(BaseModel):
    dir: str
    vote_counts: dict[str, int]
    school_directions: dict[str, str]


class BridgeForecast(BaseModel):
    as_of: str
    label: str
    target: BridgeTarget
    current_value: float | None = None
    horizons: dict[str, BridgeHorizonForecast]
    verdicts: list[BridgeVerdict]
    n_valid: int

    @property
    def is_unanimous(self) -> bool:
        return all(len(set(h.school_directions.values())) == 1 for h in self.horizons.values())


TARGET_LABELS = {
    "US_10Y_TIPS": "US 10Y TIPS Yield (实际利率)",
    "US_10Y_BEI":  "10Y Breakeven Inflation (通胀预期)",
    "DXY":         "DXY 美元综合指数",
}


def _system_prompt(school: School, target: BridgeTarget) -> str:
    from hindcast.schools import PROMPTS as XAU_PROMPTS, PHYSICAL_REALITY_ANCHORS
    base = XAU_PROMPTS[school].split("任务：基于")[0]
    stance = SCHOOL_BRIDGE_STANCE[target][school]
    task = f"\n\n**你对 {TARGET_LABELS[target]} 的立场**: {stance}\n\n"
    task += f"**任务：基于结构状态 + 宏观 + 事件窗，预测 {TARGET_LABELS[target]} 在 T+5 / T+20 的方向。**"
    return base + PHYSICAL_REALITY_ANCHORS + task + BRIDGE_OUTPUT_FORMAT


def _user_prompt(state: StructuralState, target: BridgeTarget) -> str:
    base = state.format_for_prompt()
    base += f"\n\n---\n\n**预测目标：{TARGET_LABELS[target]} 在 T+5 / T+20 的方向**"
    return base


def ask_school_bridge(client: OpenAI, school: School, state: StructuralState, target: BridgeTarget) -> BridgeVerdict:
    system_prompt = _system_prompt(school, target)
    user_prompt = _user_prompt(state, target)
    raw = chat_json(client, system_prompt, user_prompt)
    if raw.get("_failed"):
        return BridgeVerdict(
            school=school, target=target,
            verdict={"T+5": BridgeHorizon(dir="flat"), "T+20": BridgeHorizon(dir="flat")},
            _failed=True, _error=raw.get("_error"),
        )
    try:
        horizons = {h: BridgeHorizon(**raw["verdict"][h]) for h in raw.get("verdict", {})}
    except Exception as e:
        return BridgeVerdict(
            school=school, target=target,
            verdict={"T+5": BridgeHorizon(dir="flat"), "T+20": BridgeHorizon(dir="flat")},
            _failed=True, _error=f"schema: {e}",
        )
    vc = raw.get("volatility_class", "exogenous_shock")
    confidence = float(raw.get("confidence", 0.5))
    caps = {"exogenous_shock": 1.0, "endogenous_technical": 0.3,
            "stochastic_noise": 0.1, "structural_break": 0.2}
    confidence = min(confidence, caps.get(vc, 1.0))
    return BridgeVerdict(
        school=school, target=target, verdict=horizons,
        top_signals=raw.get("top_signals", []),
        volatility_class=vc,
        attribution_note=raw.get("attribution_note", ""),
        reasoning=raw.get("reasoning", ""),
        confidence=confidence,
    )


def predict_bridge(state: StructuralState, target: BridgeTarget, client: OpenAI | None = None) -> BridgeForecast:
    from hindcast.llm import get_client
    client = client or get_client()
    verdicts: list[BridgeVerdict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(ask_school_bridge, client, s, state, target): s for s in SCHOOLS}
        for fut in as_completed(futures):
            verdicts.append(fut.result())
    horizon_forecasts: dict[str, BridgeHorizonForecast] = {}
    for h in ("T+5", "T+20"):
        school_dirs = {v.school: (v.direction(h) if not v._failed else "NO_SIGNAL") for v in verdicts}
        dirs = [d for d in school_dirs.values() if d != "NO_SIGNAL"]
        if not dirs:
            winner, counts = "NO_SIGNAL", {}
        else:
            counter = Counter(dirs)
            sorted_d = sorted(counter.most_common(), key=lambda x: (-x[1], {"flat": 0, "up": 1, "down": 2}[x[0]]))
            winner, counts = sorted_d[0][0], dict(counter)
        horizon_forecasts[h] = BridgeHorizonForecast(dir=winner, vote_counts=counts, school_directions=school_dirs)
    macro = state.macro
    current = None
    if macro:
        current = {
            "US_10Y_TIPS": macro.treasury_10y_tips_yield,
            "US_10Y_BEI":  macro.breakeven_inflation_10y or macro.compute_bei_implied(),
            "DXY":         macro.dxy_index,
        }[target]
    return BridgeForecast(
        as_of=state.as_of, label=state.label, target=target,
        current_value=current,
        horizons=horizon_forecasts, verdicts=verdicts,
        n_valid=sum(1 for v in verdicts if not v._failed),
    )


def run_bridge_backtest(target: BridgeTarget, snapshots=None):
    from hindcast.data import ALL_SNAPSHOTS
    from hindcast.data.ground_truth import BRIDGE_GROUND_TRUTH
    snapshots = snapshots or [s for s in ALL_SNAPSHOTS if s.macro is not None]
    results = []
    for snap in snapshots:
        # 跳过没数据的时点（TIPS 1997+ 才有）
        if target == "US_10Y_TIPS" and (snap.macro is None or snap.macro.treasury_10y_tips_yield is None):
            print(f"\n========== {snap.label} ({snap.as_of}) — 跳过（无 TIPS 数据）==========")
            continue
        if target == "US_10Y_BEI" and (snap.macro is None or
                                        (snap.macro.breakeven_inflation_10y is None
                                         and snap.macro.compute_bei_implied() is None)):
            print(f"\n========== {snap.label} ({snap.as_of}) — 跳过（无 BEI 数据）==========")
            continue
        if target == "DXY" and (snap.macro is None or snap.macro.dxy_index is None):
            print(f"\n========== {snap.label} ({snap.as_of}) — 跳过（无 DXY 数据）==========")
            continue
        print(f"\n========== {snap.label} ({snap.as_of}) [{target}] ==========")
        forecast = predict_bridge(snap, target)
        for v in forecast.verdicts:
            if v._failed:
                print(f"  {v.school:<25} FAILED")
            else:
                print(f"  {v.school:<25} T+5: {v.verdict['T+5'].dir:<5} T+20: {v.verdict['T+20'].dir:<5}")
        gt = BRIDGE_GROUND_TRUTH.get(snap.as_of, {}).get(target, {})
        hit_t5 = forecast.horizons["T+5"].dir == gt.get("T+5", {}).get("dir")
        hit_t20 = forecast.horizons["T+20"].dir == gt.get("T+20", {}).get("dir")
        results.append({"forecast": forecast, "gt": gt, "hit_t5": hit_t5, "hit_t20": hit_t20, "label": snap.label})
    print(f"\n\n========== {target} 命中率 ==========")
    print(f"{'时点':<32} {'T+5':<10} {'GT':<10} {'hit':<5} {'T+20':<11} {'GT':<11} {'hit'}")
    print("-" * 100)
    hits_t5, hits_t20, valid = 0, 0, 0
    for r in results:
        if not r["gt"]:
            print(f"{r['label']:<32} (no GT)")
            continue
        valid += 1
        if r["hit_t5"]: hits_t5 += 1
        if r["hit_t20"]: hits_t20 += 1
        m5 = "✅" if r["hit_t5"] else "❌"
        m20 = "✅" if r["hit_t20"] else "❌"
        gt5 = r["gt"].get("T+5", {}).get("dir", "?")
        gt20 = r["gt"].get("T+20", {}).get("dir", "?")
        print(f"{r['label']:<32} {r['forecast'].horizons['T+5'].dir:<10} {gt5:<10} {m5:<5} {r['forecast'].horizons['T+20'].dir:<11} {gt20:<11} {m20}")
    print("-" * 100)
    if valid:
        total = hits_t5 + hits_t20
        print(f"T+5  命中率: {hits_t5}/{valid} = {hits_t5/valid*100:.0f}%")
        print(f"T+20 命中率: {hits_t20}/{valid} = {hits_t20/valid*100:.0f}%")
        print(f"合计 命中率: {total}/{valid*2} = {total/(valid*2)*100:.0f}%")
        print(f"W3 hard gate ≥60%: {'✅ PASS' if total/(valid*2) >= 0.6 else '❌ FAIL'}")
    return results
