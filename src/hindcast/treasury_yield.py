"""国债收益率预测（Phase 2）。

预测 US 2Y / US 10Y 在 T+5 / T+20 的方向（up / down / flat）。

设计差异（vs XAU/USD）：
  - 2Y 主要由 Fed funds expectations 折现 → 强相关于政策利率预期
  - 10Y 由 Fed funds 路径 + 通胀预期 + 增长预期 + 期限溢价共同决定
  - 危机时长端 yield 因 flight-to-safety 反而下降（与 XAU 短期相关性弱）

4 学派对收益率的立场（区别于对金价）：
  Monetarist:    yields = Fed funds 预期 + 通胀预期, 机械; 通胀升 → yields up
  Austrian:      "金融抑制"批评者; Fed 管制下 yields 低于真实水平; 危机时市场抛售 → yields up
  Keynesian:     危机时 flight-to-safety; 衰退 → 长端 yields down (但短端因降息也 down)
  Rational Exp:  曲线已 priced-in; 只有 surprise 才动; 看 Fed funds futures + dot plot
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal, Optional

from openai import OpenAI
from pydantic import BaseModel, Field

from hindcast.agents import Direction, Horizon
from hindcast.llm import chat_json
from hindcast.state import SCHOOLS, School, StructuralState


YieldTarget = Literal["US_2Y", "US_10Y"]


SCHOOL_YIELD_STANCE = {
    "austrian": """**🦘 你对国债收益率的立场**：
- 你认为 Fed 长期"金融抑制"导致 yields **低于真实水平**——真实利率应反映时间偏好 + 通胀溢价
- 通胀上升 → yields 应该 up（即使 Fed 还在 dovish 也要 up）
- 财政赤字扩大（B2 / B3）→ 主权信用风险溢价 → yields up
- 危机初期：奥地利派可能预期 yields up（市场抛售；与 Keynesian 相反）
- 你常引用 1979 Volcker（yields 飙升）/ 2022 通胀冲击作为"金融抑制崩塌"的证据
""",
    "monetarist": """**📊 你对国债收益率的立场（机械执行者）**：
- 2Y yield ≈ 未来 2 年 Fed funds 平均 + 期限溢价（小）→ 直接由货币政策预期驱动
- 10Y yield ≈ 长期 Fed funds 中性 + 通胀预期 + 期限溢价
- 通胀上升 → yields up（必要条件）
- M2 增速 / 流通速度 V 是核心隐变量
- 你常对照 Taylor implied 与当前 Fed funds 的偏离来判断 yield 方向
- 引用 1980 Volcker / 1971-80 滞胀
""",
    "keynesian": """**🏛️ 你对国债收益率的立场**：
- 经济衰退 / 失业上行 → flight-to-safety → 10Y yields **down**（即使通胀仍高）
- 失业 gap 大 → 应该降息 → 2Y yields down
- 你区分"信用主导期"和"流动性主导期"——危机模式下 yields 反而下降
- 长期低利率 + 主动财政是健康框架
- 引用 2008 雷曼后 yields 全线暴跌 / 2020 COVID yield 崩塌
""",
    "rational_expectations": """**🧮 你对国债收益率的立场**：
- 曲线 **已经 priced-in** 所有公开信息（Fed funds futures, dot plot, forward guidance）
- 看市场预期 vs Fed 预期的 spread
- 例外：当事件窗有显著 surprise（GPR spike / SDN ≥ 5）→ priced-in 不充分 → yield 可能动
- T+5 偏 flat（市场已消化）；T+20 才有定向 drift
- 你常反驳奥地利："如果 priced-in 100% inflation, 通胀上升 yields 不动"
- 引用 Lucas 1976 / Fama EMH
""",
}


YIELD_OUTPUT_FORMAT = """

---
## 🧬 深度识别模式（修 3 个系统性失败 case）

### Pattern 1: 政治压力 → Fed 转鸽（修 1971 Nixon）
当 **B1 CBI ≤ 7.0** AND policy_event_imminent AND 选举年 → Fed 可能 cut（即使 Taylor 说 hike）→ yields 跟随 **down**。

### Pattern 2: priced-in 翻转（修 2018 Trade War）
当事件已在前 30+ 天 headlines 反复出现（如 USTR 调查持续 8+ 月）→ 加息预期已 priced-in ≥80%。
新事件落地（关税）→ 主导变成"衰退担忧 → 长端 yields **down**"，不是"加息 → yields up"。
你必须显式判断"原始预期是否已经 priced-in"，再判方向。

### Pattern 3: 微弱信号 → favor flat（修 1992 ERM）
当 macro 信号都是微弱（|Taylor dev| < 0.5pp, |unemp gap| < 0.5pp）+ 无事件窗激活
→ T+5/T+20 倾向 **flat**, confidence ≤ 0.4

---
## 输出 schema (严格 JSON)

{
  "school": "<your_school>",
  "verdict": {
    "T+5":  {"dir": "up | down | flat", "range_bps": [low, high]},   // 注意 bps 不是 %
    "T+20": {"dir": "up | down | flat", "range_bps": [low, high]}
  },
  "top_signals": ["taylor_deviation", "inflation_gap", "GPR_spike", "Fed_funds_path", ...],
  "yield_curve_signal": "<1 句你对 curve slope (10Y-2Y) 走向的解读>",
  "volatility_class": "exogenous_shock | endogenous_technical | stochastic_noise | structural_break",
  "attribution_note": "<1 句: 你的方向依据，必须显式提及通胀/失业/Fed funds 路径中至少一个驱动>",
  "reasoning": "<2-3 句: 你的立场如何映射到这次 yield 方向>",
  "confidence": <0.0-1.0>
}

confidence 上限受 volatility_class 约束（ADR-002）。

不要输出 JSON 以外的任何文字。
"""


class YieldHorizon(BaseModel):
    dir: Direction
    range_bps: list[float] = Field(default_factory=lambda: [0.0, 0.0])


class YieldVerdict(BaseModel):
    school: School
    target: YieldTarget
    verdict: dict[str, YieldHorizon]                # "T+5" / "T+20" → YieldHorizon
    top_signals: list[str] = Field(default_factory=list)
    yield_curve_signal: str = ""
    volatility_class: str = "exogenous_shock"
    attribution_note: str = ""
    reasoning: str = ""
    confidence: float = 0.0
    _failed: bool = False
    _error: Optional[str] = None

    def direction(self, horizon: str) -> Direction:
        return self.verdict.get(horizon, YieldHorizon(dir="flat")).dir


class YieldHorizonForecast(BaseModel):
    dir: str
    vote_counts: dict[str, int]
    school_directions: dict[str, str]


class YieldForecast(BaseModel):
    as_of: str
    label: str
    target: YieldTarget
    current_yield: float | None = None              # 当前 yield 水平
    horizons: dict[str, YieldHorizonForecast]
    verdicts: list[YieldVerdict]
    n_valid: int

    @property
    def is_unanimous(self) -> bool:
        return all(
            len(set(h.school_directions.values())) == 1 for h in self.horizons.values()
        )

    @property
    def is_split(self) -> bool:
        for h in self.horizons.values():
            counter = Counter(h.vote_counts.values())
            if max(h.vote_counts.values()) == 2 and sum(h.vote_counts.values()) == 4:
                return True
        return False


def _system_prompt(school: School, target: YieldTarget) -> str:
    from hindcast.schools import PROMPTS as XAU_PROMPTS, PHYSICAL_REALITY_ANCHORS
    # 复用学派关注雷达 + 加 yield stance + yield output format
    base_school_prompt = XAU_PROMPTS[school].split("任务：基于")[0]
    yield_stance = SCHOOL_YIELD_STANCE[school]
    task = f"\n\n**任务：基于结构状态 + 宏观变量 + 事件窗，预测 {target} 收益率在 T+5 / T+20 的方向。**"
    return base_school_prompt + PHYSICAL_REALITY_ANCHORS + yield_stance + task + YIELD_OUTPUT_FORMAT


def _user_prompt(state: StructuralState, target: YieldTarget) -> str:
    base = state.format_for_prompt()
    base += f"\n\n---\n\n**预测目标：{target} 在 T+5 / T+20 的方向**"
    if state.macro is None or state.macro.cpi_headline_yoy is None:
        base += "\n\n⚠️ 警告：本时点 macro 数据缺失，应判 stochastic_noise + confidence ≤ 0.1"
    return base


def ask_school_yield(
    client: OpenAI, school: School, state: StructuralState, target: YieldTarget,
) -> YieldVerdict:
    system_prompt = _system_prompt(school, target)
    user_prompt = _user_prompt(state, target)

    # Optional: 注入 CausalRAG evidence（HINDCAST_USE_RAG=1）——镜像 fx.ask_school_fx。
    # target ∈ {US_2Y, US_10Y} 与 DAG asset 字段逐字一致。RAG 失败优雅降级。
    from hindcast import rag
    if rag.is_enabled():
        evidence = rag.retrieve_evidence(
            school=school,
            structural_state=state.values,
            horizon="T+5",
            target_asset=target,
        )
        if evidence and not evidence.get("_failed"):
            user_prompt += rag.format_evidence_for_prompt(evidence)

    raw = chat_json(client, system_prompt, user_prompt)
    if raw.get("_failed"):
        return YieldVerdict(
            school=school, target=target,
            verdict={"T+5": YieldHorizon(dir="flat"), "T+20": YieldHorizon(dir="flat")},
            _failed=True, _error=raw.get("_error"),
        )

    try:
        horizons = {
            h: YieldHorizon(**raw["verdict"][h])
            for h in raw.get("verdict", {})
        }
    except (KeyError, TypeError) as e:
        return YieldVerdict(
            school=school, target=target,
            verdict={"T+5": YieldHorizon(dir="flat"), "T+20": YieldHorizon(dir="flat")},
            _failed=True, _error=f"schema: {e}",
        )

    vc = raw.get("volatility_class", "exogenous_shock")
    confidence = float(raw.get("confidence", 0.5))
    caps = {"exogenous_shock": 1.0, "endogenous_technical": 0.3,
            "stochastic_noise": 0.1, "structural_break": 0.2}
    confidence = min(confidence, caps.get(vc, 1.0))

    return YieldVerdict(
        school=school,
        target=target,
        verdict=horizons,
        top_signals=raw.get("top_signals", []),
        yield_curve_signal=raw.get("yield_curve_signal", ""),
        volatility_class=vc,
        attribution_note=raw.get("attribution_note", ""),
        reasoning=raw.get("reasoning", ""),
        confidence=confidence,
    )


def majority_vote_yield(directions: list[str]) -> tuple[str, dict[str, int]]:
    valid = [d for d in directions if d != "NO_SIGNAL"]
    if not valid:
        return "NO_SIGNAL", {}
    counter = Counter(valid)
    # 平局优先：flat > up > down（保守）
    sorted_d = sorted(
        counter.most_common(),
        key=lambda x: (-x[1], {"flat": 0, "up": 1, "down": 2}[x[0]]),
    )
    return sorted_d[0][0], dict(counter)


def predict_yield(
    state: StructuralState,
    target: YieldTarget,
    horizons: list[str] | None = None,
    client: OpenAI | None = None,
) -> YieldForecast:
    """主入口：4 学派并行 → 多数投票 → YieldForecast."""
    from hindcast.llm import get_client
    horizons = horizons or ["T+5", "T+20"]
    client = client or get_client()

    verdicts: list[YieldVerdict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(ask_school_yield, client, school, state, target): school
            for school in SCHOOLS
        }
        for fut in as_completed(futures):
            verdicts.append(fut.result())

    horizon_forecasts: dict[str, YieldHorizonForecast] = {}
    for h in horizons:
        school_dirs = {
            v.school: (v.direction(h) if not v._failed else "NO_SIGNAL")
            for v in verdicts
        }
        dirs = [d for d in school_dirs.values() if d != "NO_SIGNAL"]
        winner, counts = majority_vote_yield(dirs)
        horizon_forecasts[h] = YieldHorizonForecast(
            dir=winner, vote_counts=counts, school_directions=school_dirs,
        )

    n_valid = sum(1 for v in verdicts if not v._failed)
    macro = state.macro
    current_yield = (
        macro.treasury_2y_yield if (target == "US_2Y" and macro)
        else macro.treasury_10y_yield if (target == "US_10Y" and macro)
        else None
    )

    return YieldForecast(
        as_of=state.as_of, label=state.label, target=target,
        current_yield=current_yield,
        horizons=horizon_forecasts, verdicts=verdicts, n_valid=n_valid,
    )


def run_yield_backtest(target: YieldTarget, snapshots=None):
    """跑 yield 历史回测——对每个 snapshot 跑 predict_yield, 对照 ground truth."""
    from hindcast.data import ALL_SNAPSHOTS
    from hindcast.data.ground_truth import YIELD_GROUND_TRUTH
    snapshots = snapshots or [s for s in ALL_SNAPSHOTS if s.macro is not None]
    results = []
    for snap in snapshots:
        print(f"\n========== {snap.label} ({snap.as_of}) [{target}] ==========")
        forecast = predict_yield(snap, target)
        for v in forecast.verdicts:
            if v._failed:
                print(f"  {v.school:<25} FAILED — {v._error}")
            else:
                t5 = v.verdict["T+5"]
                t20 = v.verdict["T+20"]
                print(f"  {v.school:<25} T+5: {t5.dir:<5} T+20: {t20.dir:<5}")
        gt = YIELD_GROUND_TRUTH.get(snap.as_of, {}).get(target, {})
        hit_t5 = (forecast.horizons["T+5"].dir == gt.get("T+5", {}).get("dir"))
        hit_t20 = (forecast.horizons["T+20"].dir == gt.get("T+20", {}).get("dir"))
        results.append({
            "as_of": snap.as_of, "label": snap.label, "forecast": forecast,
            "gt": gt, "hit_t5": hit_t5, "hit_t20": hit_t20,
        })
    # 总结
    print(f"\n\n========== {target} 命中率 ==========")
    print(f"{'时点':<32} {'T+5 pred':<10} {'T+5 GT':<10} {'hit':<5} {'T+20 pred':<11} {'T+20 GT':<11} {'hit'}")
    print("-" * 100)
    hits_t5, hits_t20, valid_t5, valid_t20 = 0, 0, 0, 0
    for r in results:
        if not r["gt"]:
            print(f"{r['label']:<32} (no GT)")
            continue
        gt_t5 = r["gt"].get("T+5", {}).get("dir", "?")
        gt_t20 = r["gt"].get("T+20", {}).get("dir", "?")
        pred_t5 = r["forecast"].horizons["T+5"].dir
        pred_t20 = r["forecast"].horizons["T+20"].dir
        valid_t5 += 1; valid_t20 += 1
        if r["hit_t5"]: hits_t5 += 1
        if r["hit_t20"]: hits_t20 += 1
        m5 = "✅" if r["hit_t5"] else "❌"
        m20 = "✅" if r["hit_t20"] else "❌"
        print(f"{r['label']:<32} {pred_t5:<10} {gt_t5:<10} {m5:<5} {pred_t20:<11} {gt_t20:<11} {m20}")
    print("-" * 100)
    if valid_t5:
        print(f"T+5  命中率: {hits_t5}/{valid_t5} = {hits_t5/valid_t5*100:.0f}%")
        print(f"T+20 命中率: {hits_t20}/{valid_t20} = {hits_t20/valid_t20*100:.0f}%")
        total = hits_t5 + hits_t20
        valid = valid_t5 + valid_t20
        print(f"合计 命中率: {total}/{valid} = {total/valid*100:.0f}%")
        print(f"W3 hard gate ≥60%: {'✅ PASS' if total/valid >= 0.6 else '❌ FAIL'}")
    return results
