"""大宗商品预测（Phase 3）—— COPPER + CRUDE_OIL.

核心方法论（用户原 brief）:
  - 大宗商品 = 两维交织的"中间派生变量":
    1) USD 计价: USD 强 → 商品弱
    2) 物理供给冲击: 极端天气 / 地缘政治（中东冲突 → 油价）/ 供应链

4 学派商品立场:
  Monetarist:    USD 强 → 商品弱 + 通胀预期 → 商品涨; 看 DXY + 实际利率
  Austrian:      实物锚定; 美元贬值 → 商品涨; 反映"真实"购买力
  Keynesian:     全球需求周期; 中国 PMI / 全球 GDP 增长是核心需求驱动
  Rational Exp:  futures curve 已 priced-in; 只有供给冲击 surprise 才动

特定信号:
  COPPER:    中国 PMI > 50 → 工业需求强; 全球库存 / 矿场罢工
  CRUDE_OIL: 中东 GPR / OPEC+ 决议 / 美战略石油储备 / 制裁俄罗斯
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


CommodityTarget = Literal["COPPER", "CRUDE_OIL"]


SCHOOL_COMMODITY_STANCE = {
    "austrian": """**🦘 你对大宗商品的立场（实物锚定）**:
- 商品是"真实"价值, 不是法币 noise
- 美元贬值（A2 Fed/GDP 升 / B2 财政赤字升）→ 商品名义价格涨
- 央行印钞越多 → 大宗 + 黄金涨幅越大
- 你对地缘政治敏感: 战争 / 制裁 → 油价飙升
- 引用 1973 油危机 / 1979 Iran / 2022 俄乌
""",
    "monetarist": """**📊 你对大宗商品的立场（USD 流动性）**:
- USD/X 强 → 大宗弱（计价机械）
- DXY ↑ → COPPER/OIL 跌
- Fed 加息 → USD 强 → 商品承压
- 通胀预期 ↑ → 商品 inflation hedge → 涨
- 你区分"短期 USD 强势" vs "长期实物供给"两个方向
""",
    "keynesian": """**🏛️ 你对大宗商品的立场（周期性需求）**:
- 全球经济周期决定大宗需求
- COPPER 特别敏感于**中国制造业 PMI**: PMI > 50 + 中国 GDP 强 → 铜涨; PMI < 50 → 跌
- 衰退 → 工业需求崩 → COPPER 跌
- 油价: 全球航运 + 工业用油 + 战略储备
- 你看全球 GDP 增速 + 库存周期
""",
    "rational_expectations": """**🧮 你对大宗商品的立场（futures + surprise）**:
- Futures curve 已 priced-in 所有已知信息
- 只有**供给冲击 surprise**才动价格:
  * OPEC+ 减产超预期 → 油价跳涨
  * 矿场罢工 / 矿区地震 → 铜跳涨
  * 极端天气 → 农产品跳
- 看 backwardation vs contango: backwardation = 供给紧张
- 美战略石油储备释放也是关键 surprise
""",
}


COMMODITY_OUTPUT_FORMAT = """

---
## 🧬 商品特定深度模式

### Pattern 1: 地缘政治油价主导（适用 CRUDE_OIL）
当 event_window 含中东 GPR spike / OPEC+ 决议 / 制裁俄罗斯 → 油价方向被供给冲击主导（覆盖 USD 通道）
1973 油禁运 / 1979 Iran / 2022 俄罗斯 → 油价 up; 反之解禁/增产 → down

### Pattern 2: 中国 PMI 主导铜价
当 cn_pmi_manufacturing > 51 → COPPER 倾向 up
当 cn_pmi_manufacturing < 49 → COPPER 倾向 down
2020 COVID 中国 PMI 35.7 → 铜暴跌; 2018 PMI 51.5 → 铜稳

### Pattern 3: USD 强势 → 商品压制
DXY 强势 / Fed 加息周期 + 实际利率上升 → 大宗承压
2022 Fed 加息周期 USD 强 → 铜从 9870 跌到 7000+

### Pattern 4: priced-in 翻转
长期 USD 强 已 priced-in → 实物供给冲击成新主导

---
## 输出 schema (严格 JSON)

{
  "school": "<your_school>",
  "verdict": {
    "T+5":  {"dir": "up | down | flat", "range_pct": [low, high]},
    "T+20": {"dir": "up | down | flat", "range_pct": [low, high]}
  },
  "top_signals": ["USD_DXY", "中国_PMI", "geopolitical_GPR", "supply_shock", ...],
  "supply_demand_signal": "<1 句对供需 balance 的解读>",
  "volatility_class": "exogenous_shock | endogenous_technical | stochastic_noise | structural_break",
  "attribution_note": "<1 句方向依据，必须显式提及 USD 强度 OR 供给冲击 OR 周期需求>",
  "reasoning": "<2-3 句>",
  "confidence": <0.0-1.0>
}

confidence 上限受 volatility_class 约束（ADR-002）。
不要输出 JSON 以外的任何文字。
"""


class CommodityHorizon(BaseModel):
    dir: Direction
    range_pct: list[float] = Field(default_factory=lambda: [0.0, 0.0])


class CommodityVerdict(BaseModel):
    school: School
    target: CommodityTarget
    verdict: dict[str, CommodityHorizon]
    top_signals: list[str] = Field(default_factory=list)
    supply_demand_signal: str = ""
    volatility_class: str = "exogenous_shock"
    attribution_note: str = ""
    reasoning: str = ""
    confidence: float = 0.0
    _failed: bool = False
    _error: Optional[str] = None

    def direction(self, horizon: str) -> Direction:
        return self.verdict.get(horizon, CommodityHorizon(dir="flat")).dir


class CommodityHorizonForecast(BaseModel):
    dir: str
    vote_counts: dict[str, int]
    school_directions: dict[str, str]


class CommodityForecast(BaseModel):
    as_of: str
    label: str
    target: CommodityTarget
    current_price: float | None = None
    horizons: dict[str, CommodityHorizonForecast]
    verdicts: list[CommodityVerdict]
    n_valid: int

    @property
    def is_unanimous(self) -> bool:
        return all(len(set(h.school_directions.values())) == 1 for h in self.horizons.values())


def _system_prompt(school: School, target: CommodityTarget) -> str:
    from hindcast.schools import PROMPTS as XAU_PROMPTS, PHYSICAL_REALITY_ANCHORS
    base = XAU_PROMPTS[school].split("任务：基于")[0]
    stance = SCHOOL_COMMODITY_STANCE[school]
    target_label = "WTI 原油" if target == "CRUDE_OIL" else "LME 铜"
    task = f"\n\n**任务：预测 {target_label} 价格在 T+5 / T+20 的方向。**"
    return base + PHYSICAL_REALITY_ANCHORS + stance + task + COMMODITY_OUTPUT_FORMAT


def _user_prompt(state: StructuralState, target: CommodityTarget) -> str:
    base = state.format_for_prompt()
    base += f"\n\n---\n\n**预测目标：{target} 在 T+5 / T+20 的方向**"
    return base


def ask_school_commodity(client: OpenAI, school: School, state: StructuralState, target: CommodityTarget) -> CommodityVerdict:
    system_prompt = _system_prompt(school, target)
    user_prompt = _user_prompt(state, target)

    # Optional: 注入 CausalRAG evidence（HINDCAST_USE_RAG=1）——镜像 fx.ask_school_fx。
    # DAG 里原油节点名为 WTI（非本文件 target 的 CRUDE_OIL）；COPPER 一致。RAG 失败优雅降级。
    from hindcast import rag
    if rag.is_enabled():
        evidence = rag.retrieve_evidence(
            school=school,
            structural_state=state.values,
            horizon="T+5",
            target_asset=("WTI" if target == "CRUDE_OIL" else target),
        )
        if evidence and not evidence.get("_failed"):
            user_prompt += rag.format_evidence_for_prompt(evidence)
    raw = chat_json(client, system_prompt, user_prompt)
    if raw.get("_failed"):
        return CommodityVerdict(
            school=school, target=target,
            verdict={"T+5": CommodityHorizon(dir="flat"), "T+20": CommodityHorizon(dir="flat")},
            _failed=True, _error=raw.get("_error"),
        )
    try:
        horizons = {h: CommodityHorizon(**raw["verdict"][h]) for h in raw.get("verdict", {})}
    except Exception as e:
        return CommodityVerdict(
            school=school, target=target,
            verdict={"T+5": CommodityHorizon(dir="flat"), "T+20": CommodityHorizon(dir="flat")},
            _failed=True, _error=f"schema: {e}",
        )
    vc = raw.get("volatility_class", "exogenous_shock")
    confidence = float(raw.get("confidence", 0.5))
    caps = {"exogenous_shock": 1.0, "endogenous_technical": 0.3,
            "stochastic_noise": 0.1, "structural_break": 0.2}
    confidence = min(confidence, caps.get(vc, 1.0))
    return CommodityVerdict(
        school=school, target=target, verdict=horizons,
        top_signals=raw.get("top_signals", []),
        supply_demand_signal=raw.get("supply_demand_signal", ""),
        volatility_class=vc,
        attribution_note=raw.get("attribution_note", ""),
        reasoning=raw.get("reasoning", ""),
        confidence=confidence,
    )


def predict_commodity(state: StructuralState, target: CommodityTarget, client: OpenAI | None = None) -> CommodityForecast:
    from hindcast.llm import get_client
    client = client or get_client()
    verdicts: list[CommodityVerdict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(ask_school_commodity, client, s, state, target): s for s in SCHOOLS}
        for fut in as_completed(futures):
            verdicts.append(fut.result())
    horizon_forecasts: dict[str, CommodityHorizonForecast] = {}
    for h in ("T+5", "T+20"):
        school_dirs = {v.school: (v.direction(h) if not v._failed else "NO_SIGNAL") for v in verdicts}
        dirs = [d for d in school_dirs.values() if d != "NO_SIGNAL"]
        if not dirs:
            winner, counts = "NO_SIGNAL", {}
        else:
            counter = Counter(dirs)
            sorted_d = sorted(counter.most_common(), key=lambda x: (-x[1], {"flat": 0, "up": 1, "down": 2}[x[0]]))
            winner, counts = sorted_d[0][0], dict(counter)
        horizon_forecasts[h] = CommodityHorizonForecast(dir=winner, vote_counts=counts, school_directions=school_dirs)
    macro = state.macro
    current = (macro.crude_oil_wti_usd if target == "CRUDE_OIL" else macro.copper_lme_usd_t) if macro else None
    return CommodityForecast(
        as_of=state.as_of, label=state.label, target=target,
        current_price=current,
        horizons=horizon_forecasts, verdicts=verdicts,
        n_valid=sum(1 for v in verdicts if not v._failed),
    )


def run_commodity_backtest(target: CommodityTarget, snapshots=None):
    from hindcast.data import ALL_SNAPSHOTS
    from hindcast.data.ground_truth import COMMODITY_GROUND_TRUTH
    snapshots = snapshots or [s for s in ALL_SNAPSHOTS if s.macro is not None]
    results = []
    for snap in snapshots:
        print(f"\n========== {snap.label} ({snap.as_of}) [{target}] ==========")
        forecast = predict_commodity(snap, target)
        for v in forecast.verdicts:
            if v._failed:
                print(f"  {v.school:<25} FAILED")
            else:
                print(f"  {v.school:<25} T+5: {v.verdict['T+5'].dir:<5} T+20: {v.verdict['T+20'].dir:<5}")
        gt = COMMODITY_GROUND_TRUTH.get(snap.as_of, {}).get(target, {})
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
