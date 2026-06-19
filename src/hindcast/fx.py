"""外汇预测（Phase 3）—— USD/CNH + USD/JPY 方向预测。

核心方法论（用户原 brief）:
  - Meese-Rogoff puzzle: 传统 FX 模型败给 random walk
  - 但 Taylor differential 模型 (US - 对方 Taylor implied rate) 显著击败 random walk
  - **FX 是派生变量**: 必须先准确预测两国政策利率, FX 方向才稳固

4 学派 FX 立场:
  Monetarist:    Taylor differential 机械; US-X 差值越大 USD 升值
  Austrian:      法币比烂; 哪国 CBI 更低 / 财政更差 / 印钞更猛 → 该国货币贬
  Keynesian:     贸易余额 + 国际收支 + 经常项; 出口国货币升值
  Rational Exp:  forward rate / interest rate parity 已 priced-in
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


FXTarget = Literal["USD/CNH", "USD/JPY", "EUR/USD"]

# ⚠️ 报价方向约定（不同 target 不一样）:
#   USD/CNH / USD/JPY : dir=up → USD 升值（报价升高）, 对手货币贬值
#   EUR/USD           : dir=up → EUR/USD 报价升高 → **EUR 升值 / USD 贬值**（与上面相反!）
_USD_BASE = {"USD/CNH", "USD/JPY"}     # USD 作为基准货币的 pair


SCHOOL_FX_STANCE = {
    "austrian": """**🦘 你对 FX 的立场（"法币比烂" + 管制识别）**:
- 自由浮动汇率: 哪国央行印钞更猛 / CBI 更低 → 该国货币贬值
- **USD/CNH = 管制汇率, 不是市场变量**: 默认 **flat**（T+5/T+20 都 flat 是 base case）, 除非有显式政策事件
- USD/JPY 平时偏 up（carry funding），但危机时 JPY safe haven → USD/JPY down
- **2022 后例外**: Japan 转为慢性经常项赤字国 + 能源冲击 → safe haven 失效（见 Pattern 6）
- **EUR/USD**（dir=up=EUR强USD弱, 与JPY相反）: 欧元区无财政联盟 + 外围债务货币化 → 结构性 EUR 弱; 危机时 USD 储备货币优势 → EUR/USD **down**
- 引用 1971 弃锚 / 2008 yen 急涨 / 2015 8/11 汇改（罕见 CNH 急跌）/ 2022 Russia (Pattern 6)
""",
    "monetarist": """**📊 你对 FX 的立场（Taylor differential 但承认管制扰动）**:
- 自由浮动 FX: Taylor differential → 方向
- **USD/CNH**: PBoC 管制让 Taylor differential 失效——默认 **flat**, 不要按 US-CN diff 给 up
- **JPY 例外**: 危机期 carry unwind → USD/JPY 跌, 不能按 Taylor diff 直接给 up
- **2022 后例外**: Japan 慢性经常项赤字 + 能源冲击 → 即使危机 USD/JPY 仍 up (见 Pattern 6)
- **EUR/USD**（dir=up=EUR强USD弱）: US-EU Taylor diff 机械——Fed 比 ECB 更鹰 (diff>0) → USD 强 → EUR/USD **down**; ECB 历史上滞后 Fed
- 1981 USD 飙升 / 2008 yen 急涨（打破 Taylor differential 的两种场景）
""",
    "keynesian": """**🏛️ 你对 FX 的立场（贸易 + safe haven + 管制）**:
- 自由浮动: 贸易顺差大国货币长期升值, 危机期 safe haven 升值
- **CNH**: 管制汇率，**T+5 AND T+20 默认 flat**; 只有政策事件（汇改/中美贸易战升级/资本外逃恐慌）才允许给方向
- **JPY**: G10 风险偏好反向指标——危机→USD/JPY down
- **关键物理事实**: Japan 100% 能源进口; 但**是否影响汇率**取决于经常项结构
  - 1979 时代: Japan 制造业顺差强 → 油价飙也扛得住, JPY 升
  - 2022 时代: Japan 慢性逆差 + 老龄化 → 油价飙瞬间放大贬值 (Pattern 6)
- 1979 yen 升值因日本通胀降幅快 + 经常项顺差转向
- **EUR/USD**（dir=up=EUR强USD弱）: 平时德国经常项顺差 → EUR 支撑; 但欧元区**能源依赖俄罗斯**（见物理现实锚）→ 能源冲击→贸易条件崩→EUR **down**（2022 与 JPY Pattern 6 同构）; 财政分散→ECB 受掣肘
""",
    "rational_expectations": """**🧮 你对 FX 的立场（priced-in + 政策驱动）**:
- 自由浮动: forward rate 已 priced-in 利率差; 只有 surprise 才动
- **USD/CNH = 政策驱动**, 不是市场——PBoC 中间价是核心信号; **默认 flat 是理性预期**, 因为 PBoC 优先于市场
- **JPY**: carry unwind 是非线性触发器（VIX > 30 / 危机事件 → JPY 急涨）
- **2022 后例外**: Japan 经常项结构性翻转 + 能源冲击 → carry unwind 反向 (见 Pattern 6)
- 1971 弃锚是结构性 surprise → USD/JPY 长期大跌
- **EUR/USD**（dir=up=EUR强USD弱）: 利差已 priced-in (ECB forward guidance / Draghi "whatever it takes"); 只有 surprise 才动——危机=美元 funding 挤压 surprise → EUR/USD 急 **down** (2008 教科书)
""",
}


FX_OUTPUT_FORMAT = """

---
## 🧬 深度识别模式

### Pattern 1: 政治压力 → CBI 受损 → 该国货币贬值
当 B1 CBI ≤ 7.0 + 选举年/政治施压 → 该国货币长期看贬
1971 USD/JPY 应大跌（弃锚）; 2018+ USD 韧性较强是结构性例外

### Pattern 2: priced-in 翻转
当 Fed 加息路径已 priced-in ≥30 日 → USD 强势可能 fade
关税担忧 → 衰退预期 → DXY 回落 → USD/CNH USD/JPY 下行

### Pattern 3: 微弱信号
|Taylor diff| < 0.5pp + 无事件窗激活 → 倾向 flat, confidence ≤ 0.4

### 🔥 Pattern 4: CNH 管制汇率 — 默认 flat（USD/CNH 核心方法论）
**USD/CNH 不是市场变量, 是政策变量**：
- PBoC 每日 9:15 中间价 + ±2% 波动带 + 资本账户有限开放
- **默认立场**: T+5 AND T+20 都倾向 **flat**, confidence ≥ 0.6
- **不要**按 Taylor differential 给方向——PBoC 优先于自由市场
- **只有以下显式触发器才允许给 up/down**:
  1. event_window 含 "汇改" / "中间价 ±0.5% 改变" / "PBoC 政策决议" / "资本外逃恐慌"
  2. economic_policy_signals 含 "exchange_rate_regime_change" 类信号
  3. 中美关税战升级 + 中国出口受冲击 → PBoC 可能允许贬值 (T+20 up)
- 危机期（2008/2020/2022): USD 全市场跌, USD/CNH 可能轻微 down 但通常仍 flat
- 历史例外（罕见）:
  * 2015-08-11 汇改 → USD/CNH 三日 +3%
  * 2018 中美贸易战 → PBoC 反向中间价后 CNH 短期下行
- **如果没有以上触发器, 强制 flat + attribution 必须显式写"PBoC 管制下默认 flat, 无政策触发器"**

### 🔥 Pattern 5: JPY safe haven + carry unwind（USD/JPY 必读）
**日元的双重身份：carry trade funding currency + safe haven**：
- 平时（risk-on 周期）: JPY 是 carry funding → USD/JPY up（卖 JPY 买高息）
- 危机/risk-off（VIX > 30 / GPR spike / 金融系统性事件）: **carry unwind → JPY 急涨 → USD/JPY 急跌**
  * 例: 2008 雷曼 → USD/JPY -8% (yen 急涨)
  * 例: 2020 COVID → USD/JPY -2 to -5%
- **不要无脑按 Taylor diff 给 USD/JPY up** —— Volcker shock (1979) 期间 USD/JPY 反而下跌（日本通胀降幅快 + 经常项顺差转向）
- 1971 弃锚后 USD/JPY 大跌（Smithsonian 协议重定汇率）
- 触发危机识别信号: event_window 含 financial_crisis / GPR spike / 央行紧急动作 ≥ 3

### 🔥 Pattern 6: 能源冲击 → JPY safe haven 失效（修 2022 Russia case）
**核心物理事实**: Japan **100% 能源进口 + 60% 食品进口** → 油价飙 = Japan 贸易逆差恶化 = 必须卖 JPY 买美元买能源
当满足以下**全部**（窄触发, 避免与 1979 Volcker 混淆）→ **JPY safe haven 失效, USD/JPY up**:
- event_window 含**能源相关** GPR spike（俄乌战争 / 中东冲突 / OPEC+ 减产 / 能源禁运）
- AND Japan 此时已是**慢性经常项赤字国**（2022 时代特征: 老龄化 + 制造业外迁 + 贸易逆差结构化）
- AND WTI 或 Brent 油价 30 日变化 > +20%
→ "卖 JPY 买能源"的 flow > "避险买 JPY"的 flow
→ 2022 俄乌教科书案例: USD/JPY 115 → 150 (+30%)
→ **反例区分**: 1979 油价虽飙, 但 Japan 当时**制造业出口顺差强**, 经常项扛得住, 反而 JPY 升
→ **判断关键**: 不只看油价, 必须看 Japan 经常项是否**结构性赤字**

### 🔥 Pattern 7: EUR 真·能源冲击 → EUR/USD down（窄触发, 与 JPY Pattern 6 同构）
**仅适用 EUR/USD**（dir=up=EUR强USD弱, 注意与 USD/JPY 报价方向相反）。核心物理事实（见物理现实锚）:
欧元区**能源高度依赖俄罗斯**（战前天然气 ~40%）+ **货币联盟无财政联盟**（ECB 加息空间结构性小于 Fed）。
当满足以下**全部**（窄触发, 仿 JPY Pattern 6, 避免误伤纯流动性/降息型危机）→ **EUR/USD down**:
- event_window 含**能源相关** GPR spike（俄乌战争 / 中东冲突 / 天然气断供 / 能源禁运）
- AND WTI 或 Brent 油价 30 日变化 > +20%
- AND 该冲击直接打击欧元区贸易条件（欧元区为受冲击的能源净进口方）
→ 欧元区贸易条件崩 + ECB 受掣肘 → EUR/USD **down**
  * 2022 俄乌教科书: EUR/USD 1.13 → 0.96 (跌破平价), 与 USD/JPY 同期大涨**同构**
→ **反例区分（关键, 不得一刀切）**: 纯流动性/降息型危机**不算**能源冲击——
  2020 COVID 是无限 QE → USD 走弱, 中期 EUR/USD 实际 **up**; 此时**不得默认 down**
- **判断顺序**: (1) 上述三条件**全部命中**? → down  (2) 否则**以检索到的 CausalRAG supports 的 aggregate 方向为准**（如 m_easing_speed aggregate + → up）, **不得仅因"有危机"就给 down**  (3) 无 RAG 证据时才回退到 US-EU 利差与德国经常项
- ⚠️ EUR 1999 才诞生, 不要对 pre-1999 时点给 EUR/USD 预测

---
## 输出 schema (严格 JSON)

{
  "school": "<your_school>",
  "verdict": {
    "T+5":  {"dir": "up | down | flat", "range_pct": [low_pct, high_pct]},
    "T+20": {"dir": "up | down | flat", "range_pct": [low_pct, high_pct]}
  },
  "top_signals": ["taylor_differential", "policy_rate_path", "GPR", ...],
  "taylor_diff_signal": "<1 句对 US-X Taylor differential 的解读>",
  "volatility_class": "exogenous_shock | endogenous_technical | stochastic_noise | structural_break",
  "attribution_note": "<1 句方向依据，必须显式提及 Taylor diff 或 carry trade 或 央行干预>",
  "reasoning": "<2-3 句>",
  "confidence": <0.0-1.0>
}

注: dir=up 意味 USD 升值（USD/CNH 升 / USD/JPY 升）即对手货币贬值。
confidence 上限受 volatility_class 约束（ADR-002）。
不要输出 JSON 以外的任何文字。
"""


class FXHorizon(BaseModel):
    dir: Direction
    range_pct: list[float] = Field(default_factory=lambda: [0.0, 0.0])


class FXVerdict(BaseModel):
    school: School
    target: FXTarget
    verdict: dict[str, FXHorizon]
    top_signals: list[str] = Field(default_factory=list)
    taylor_diff_signal: str = ""
    volatility_class: str = "exogenous_shock"
    attribution_note: str = ""
    reasoning: str = ""
    confidence: float = 0.0
    _failed: bool = False
    _error: Optional[str] = None

    def direction(self, horizon: str) -> Direction:
        return self.verdict.get(horizon, FXHorizon(dir="flat")).dir


class FXHorizonForecast(BaseModel):
    dir: str
    vote_counts: dict[str, int]
    school_directions: dict[str, str]


class FXForecast(BaseModel):
    as_of: str
    label: str
    target: FXTarget
    current_spot: float | None = None
    taylor_differential: float | None = None
    horizons: dict[str, FXHorizonForecast]
    verdicts: list[FXVerdict]
    n_valid: int

    @property
    def is_unanimous(self) -> bool:
        return all(len(set(h.school_directions.values())) == 1 for h in self.horizons.values())


def _system_prompt(school: School, target: FXTarget) -> str:
    from hindcast.schools import PROMPTS as XAU_PROMPTS, PHYSICAL_REALITY_ANCHORS
    base = XAU_PROMPTS[school].split("任务：基于")[0]
    fx_stance = SCHOOL_FX_STANCE[school]
    task = f"\n\n**任务：基于结构状态 + 宏观（US + 对方国）+ event_window，预测 {target} 在 T+5 / T+20 的方向。**\n"
    if target in _USD_BASE:
        task += f"注: dir=up 意味 USD 升值（{target} 报价升高），对手货币贬值。"
    else:  # EUR/USD
        task += "注: dir=up 意味 **EUR/USD 报价升高 → EUR 升值 / USD 贬值**（与 USD/JPY 报价方向相反!）。"
    return base + PHYSICAL_REALITY_ANCHORS + fx_stance + task + FX_OUTPUT_FORMAT


def _user_prompt(state: StructuralState, target: FXTarget) -> str:
    base = state.format_for_prompt()
    # EU macro + US-EU Taylor differential 在 state.format_for_prompt 中嵌套于 prior_section
    # (XAU 集成专用), FX 路径不触发——故对 EUR/USD 在此处显式注入。
    if target == "EUR/USD" and state.macro is not None:
        m = state.macro
        if m.eu_cpi_yoy is not None:
            eu_t = m.compute_taylor_implied_eu()
            us_t = m.compute_taylor_implied()
            diff = m.us_eu_taylor_differential()
            lines = ["", "### 🇪🇺 欧元区 macro（EUR/USD 预测核心）"]
            lines.append(
                f"- EU: CPI {m.eu_cpi_yoy:.1f}% / ECB 利率 {m.eu_policy_rate}% / GDP {m.eu_gdp_growth_yoy}% / 产出 gap {m.eu_output_gap_pct}%"
                + (f" / Taylor implied **{eu_t:.2f}%**" if eu_t is not None else "")
            )
            if diff is not None:
                bias = "USD 升值压力 → EUR/USD **down**" if diff > 1 else (
                    "USD 贬值压力 → EUR/USD **up**" if diff < -1 else "中性")
                lines.append(
                    f"- **🧮 US-EU Taylor differential: {diff:+.2f} pp**（US implied {us_t:.2f}% − EU implied {eu_t:.2f}%）→ {bias}"
                )
            base += "\n" + "\n".join(lines)
    base += f"\n\n---\n\n**预测目标：{target} 在 T+5 / T+20 的方向**"
    return base


def ask_school_fx(client: OpenAI, school: School, state: StructuralState, target: FXTarget) -> FXVerdict:
    system_prompt = _system_prompt(school, target)
    user_prompt = _user_prompt(state, target)

    # Optional: 注入 CausalRAG evidence（HINDCAST_USE_RAG=1）——镜像 agents.ask_school。
    # target_asset 传真实 FX target（不再硬编码 XAU/USD）。RAG 失败优雅降级。
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
        return FXVerdict(
            school=school, target=target,
            verdict={"T+5": FXHorizon(dir="flat"), "T+20": FXHorizon(dir="flat")},
            _failed=True, _error=raw.get("_error"),
        )
    try:
        horizons = {h: FXHorizon(**raw["verdict"][h]) for h in raw.get("verdict", {})}
    except Exception as e:
        return FXVerdict(
            school=school, target=target,
            verdict={"T+5": FXHorizon(dir="flat"), "T+20": FXHorizon(dir="flat")},
            _failed=True, _error=f"schema: {e}",
        )
    vc = raw.get("volatility_class", "exogenous_shock")
    confidence = float(raw.get("confidence", 0.5))
    caps = {"exogenous_shock": 1.0, "endogenous_technical": 0.3,
            "stochastic_noise": 0.1, "structural_break": 0.2}
    confidence = min(confidence, caps.get(vc, 1.0))
    return FXVerdict(
        school=school, target=target, verdict=horizons,
        top_signals=raw.get("top_signals", []),
        taylor_diff_signal=raw.get("taylor_diff_signal", ""),
        volatility_class=vc,
        attribution_note=raw.get("attribution_note", ""),
        reasoning=raw.get("reasoning", ""),
        confidence=confidence,
    )


def predict_fx(state: StructuralState, target: FXTarget, client: OpenAI | None = None) -> FXForecast:
    from hindcast.llm import get_client
    client = client or get_client()
    verdicts: list[FXVerdict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(ask_school_fx, client, s, state, target): s for s in SCHOOLS}
        for fut in as_completed(futures):
            verdicts.append(fut.result())
    horizon_forecasts: dict[str, FXHorizonForecast] = {}
    for h in ("T+5", "T+20"):
        school_dirs = {v.school: (v.direction(h) if not v._failed else "NO_SIGNAL") for v in verdicts}
        dirs = [d for d in school_dirs.values() if d != "NO_SIGNAL"]
        if not dirs:
            winner, counts = "NO_SIGNAL", {}
        else:
            counter = Counter(dirs)
            sorted_d = sorted(counter.most_common(), key=lambda x: (-x[1], {"flat": 0, "up": 1, "down": 2}[x[0]]))
            winner, counts = sorted_d[0][0], dict(counter)
        horizon_forecasts[h] = FXHorizonForecast(dir=winner, vote_counts=counts, school_directions=school_dirs)
    macro = state.macro
    if not macro:
        current = taylor_diff = None
    elif target == "USD/CNH":
        current, taylor_diff = macro.usd_cnh_spot, macro.us_cn_taylor_differential()
    elif target == "USD/JPY":
        current, taylor_diff = macro.usd_jpy_spot, macro.us_jp_taylor_differential()
    else:  # EUR/USD
        current, taylor_diff = macro.eur_usd_spot, macro.us_eu_taylor_differential()
    return FXForecast(
        as_of=state.as_of, label=state.label, target=target,
        current_spot=current, taylor_differential=taylor_diff,
        horizons=horizon_forecasts, verdicts=verdicts,
        n_valid=sum(1 for v in verdicts if not v._failed),
    )


def run_fx_backtest(target: FXTarget, snapshots=None):
    from hindcast.data import ALL_SNAPSHOTS
    from hindcast.data.ground_truth import FX_GROUND_TRUTH
    snapshots = snapshots or [s for s in ALL_SNAPSHOTS if s.macro is not None]
    results = []
    for snap in snapshots:
        # 跳过没 FX 数据的早期时点
        if target == "USD/CNH" and (snap.macro is None or snap.macro.usd_cnh_spot is None):
            print(f"\n========== {snap.label} ({snap.as_of}) — 跳过（无 USD/CNH 数据）==========")
            continue
        if target == "USD/JPY" and (snap.macro is None or snap.macro.usd_jpy_spot is None):
            print(f"\n========== {snap.label} ({snap.as_of}) — 跳过（无 USD/JPY 数据）==========")
            continue
        if target == "EUR/USD" and (snap.macro is None or snap.macro.eur_usd_spot is None):
            print(f"\n========== {snap.label} ({snap.as_of}) — 跳过（EUR 1999 才诞生 / 无数据）==========")
            continue
        print(f"\n========== {snap.label} ({snap.as_of}) [{target}] ==========")
        forecast = predict_fx(snap, target)
        for v in forecast.verdicts:
            if v._failed:
                print(f"  {v.school:<25} FAILED")
            else:
                print(f"  {v.school:<25} T+5: {v.verdict['T+5'].dir:<5} T+20: {v.verdict['T+20'].dir:<5}")
        gt = FX_GROUND_TRUTH.get(snap.as_of, {}).get(target, {})
        hit_t5 = forecast.horizons["T+5"].dir == gt.get("T+5", {}).get("dir")
        hit_t20 = forecast.horizons["T+20"].dir == gt.get("T+20", {}).get("dir")
        results.append({"forecast": forecast, "gt": gt, "hit_t5": hit_t5, "hit_t20": hit_t20, "label": snap.label})
    print(f"\n\n========== {target} 命中率 ==========")
    print(f"{'时点':<32} {'T+5':<10} {'T+5 GT':<10} {'hit':<5} {'T+20':<11} {'T+20 GT':<11} {'hit'}")
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
