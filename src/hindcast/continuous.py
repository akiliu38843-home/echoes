"""平稳期滚动回测（Phase 5）—— 不局限于 9 个戏剧性事件，按月连续打分。

动机（用户原话）：戏剧性事件测的是"大事来了抓不抓得住"；
平稳期连续测的是"没事的时候会不会瞎报信号"（反幻觉协议 ADR-002 的连续检验）。

数据来源：factual_rag (:8002) /state/asof —— 可还原任意历史日期的经济状态 +
金价/汇率点位。用 D / D+7 / D+30 三次点位查询自动算"该涨该跌该平"当答案。

诚实声明（必读）：
- 14 个缓变结构变量 (A1-E2) factual_rag 没有 → 用最近的 2018-03 快照定值
  （平稳期这些月/季度级慢变量影响小，但这是一个简化假设）
- core_pce 用 core CPI 近似；GDP 用 yoy 近似 qoq —— 仅影响 Taylor（对 FX 本就是死代码）
- T+5 ≈ +7 自然日、T+20 ≈ +30 自然日（factual_rag 自动回退到最近交易日），非精确交易日
- flat 阈值见 FLAT_PCT，会同时打印真实涨跌幅分布以便判断阈值是否合理
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

import requests

from hindcast.state import StructuralState, MacroEconomic

FACTUAL_RAG = "http://127.0.0.1:8002"
_NOPROXY = {"http": None, "https": None}

# 自由浮动 FX flat 阈值（绝对涨跌幅 < 此值算 flat）
FLAT_PCT = {"T+5": 0.5, "T+20": 1.0}
# horizon → 自然日偏移（factual_rag 回退到最近交易日）
HORIZON_DAYS = {"T+5": 7, "T+20": 30}

# target → factual_rag level_2 价格 var_id
_PRICE_VAR = {
    "USD/JPY": "usdjpy_spot",
    "EUR/USD": "eurusd_spot",
    "USD/CNH": "usdcnh_spot",
    "XAU/USD": "xau_usd_spot",
}


def _fr_state(date: str) -> Optional[dict]:
    try:
        r = requests.get(f"{FACTUAL_RAG}/state/asof", params={"date": date},
                          timeout=10, proxies=_NOPROXY)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"  [factual_rag] {date} 取数失败: {e}")
    return None


def _v(fr: dict, level: str, key: str):
    node = (fr or {}).get(level, {}).get(key)
    return node.get("value") if isinstance(node, dict) else None


def _price(fr: dict, var: str) -> Optional[float]:
    return _v(fr, "level_2", var)


def build_state_asof(date: str, fr: dict) -> StructuralState:
    """factual_rag /state/asof → hindcast StructuralState（FX 预测所需字段）。"""
    from hindcast.data import SNAPSHOTS
    # 14 缓变结构变量：用 2018-03 快照定值（平稳期慢变量，简化假设）
    struct_vals = dict(SNAPSHOTS["2018-03-21"].values)

    macro = MacroEconomic(
        cpi_headline_yoy=_v(fr, "level_0", "us_cpi_yoy"),
        core_pce_yoy=_v(fr, "level_0", "us_core_cpi_yoy"),       # core CPI 近似
        unemployment_rate=_v(fr, "level_0", "us_unemployment"),
        gdp_growth_qoq_annualized=_v(fr, "level_0", "us_gdp_yoy"),  # yoy 近似
        current_fed_funds_target=_v(fr, "level_1", "fed_funds_target_upper")
                                  or _v(fr, "level_1", "fed_funds_rate"),
        treasury_2y_yield=_v(fr, "level_2", "us_2y_yield"),
        treasury_10y_yield=_v(fr, "level_2", "us_10y_yield"),
        dxy_index=_v(fr, "level_2", "dxy_index"),
        usd_jpy_spot=_v(fr, "level_2", "usdjpy_spot"),
        eur_usd_spot=_v(fr, "level_2", "eurusd_spot"),
        usd_cnh_spot=_v(fr, "level_2", "usdcnh_spot"),
        crude_oil_wti_usd=_v(fr, "level_2", "wti_crude"),
        copper_lme_usd_t=_v(fr, "level_2", "copper_lme"),
        jp_policy_rate=_v(fr, "level_1", "boj_short_rate"),
    )
    return StructuralState(
        as_of=date,
        label=f"平稳期连续 {date}",
        values=struct_vals,
        macro=macro,
    )


def _shift(date: str, days: int) -> str:
    d = _dt.date.fromisoformat(date) + _dt.timedelta(days=days)
    return d.isoformat()


# ── 学派账本接线（17-ADR A：让账本可信）─────────────────────────────
# 连续平稳期回测里把**每个学派单独的方向**写成 school_ledger.py 能解析的块，
# 并内嵌当月真实方向（__GT__ 行）——因为连续点的日期不在静态 GROUND_TRUTH 字典里，
# 真值只能来自本回测当场用 factual_rag 算出的 gt5/gt20。
#
# 为什么要它：现有学派账本是用手挑的 9 个戏剧事件算的，有"事件选择偏差"。
# 连续平稳期数据没有这个偏差 → 这才是 17-ADR §4 铁律要求的、可信的学派账本来源。
# 纯增量：__GT__ 不匹配 ledger 的学派行正则，老的 9 事件路径完全不受影响。
_LEDGER_SCHOOLS = ("austrian", "monetarist", "keynesian", "rational_expectations")


def _emit_school_block(target: str, date: str, fc, gt5: str, gt20: str) -> None:
    """打印一个 school_ledger.py 可解析的 per-school 块（连续平稳期，内嵌真值）。"""
    sd5 = fc.horizons["T+5"].school_directions
    sd20 = fc.horizons["T+20"].school_directions
    print(f"========== 平稳期连续 ({date}) [{target}] ==========")
    print(f"  __GT__                  T+5: {gt5:<5} T+20: {gt20:<5}  [连续真值·无事件选择偏差]")
    for s in _LEDGER_SCHOOLS:
        d5 = sd5.get(s, "NO_SIGNAL")
        d20 = sd20.get(s, "NO_SIGNAL")
        print(f"  {s:<22}  T+5: {d5:<5} T+20: {d20:<5}")


def _actual_dir(base_price: float, fut_price: float, flat_pct: float) -> tuple[str, float]:
    if base_price is None or fut_price is None or base_price == 0:
        return "?", 0.0
    pct = (fut_price - base_price) / base_price * 100.0
    if abs(pct) < flat_pct:
        return "flat", pct
    return ("up" if pct > 0 else "down"), pct


def _month_points(start_ym: str, end_ym: str, day: int = 15) -> list[str]:
    sy, sm = map(int, start_ym.split("-"))
    ey, em = map(int, end_ym.split("-"))
    out = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}-{day:02d}")
        m += 1
        if m > 12:
            m = 1; y += 1
    return out


def run_continuous_backtest(target: str = "USD/JPY",
                            start_ym: str = "2016-06", end_ym: str = "2018-01"):
    """平稳期月度滚动回测。target 限 FX（USD/JPY/EUR/USD/USD/CNH/XAU/USD）。"""
    from hindcast.fx import predict_fx
    pvar = _PRICE_VAR.get(target)
    if pvar is None:
        print(f"ERROR: 暂只支持 {list(_PRICE_VAR)}")
        return

    dates = _month_points(start_ym, end_ym)
    print(f"平稳期连续回测 [{target}] {start_ym}→{end_ym}  共 {len(dates)} 个月度点")
    print(f"flat 阈值: T+5 <{FLAT_PCT['T+5']}% / T+20 <{FLAT_PCT['T+20']}%  "
          f"(factual_rag 喂数据, 14 结构变量用 2018-03 定值)\n")

    rows = []
    for d in dates:
        fr0 = _fr_state(d)
        if fr0 is None:
            continue
        p0 = _price(fr0, pvar)
        fr5 = _fr_state(_shift(d, HORIZON_DAYS["T+5"]))
        fr20 = _fr_state(_shift(d, HORIZON_DAYS["T+20"]))
        gt5, m5 = _actual_dir(p0, _price(fr5, pvar) if fr5 else None, FLAT_PCT["T+5"])
        gt20, m20 = _actual_dir(p0, _price(fr20, pvar) if fr20 else None, FLAT_PCT["T+20"])

        state = build_state_asof(d, fr0)
        fc = predict_fx(state, target)  # type: ignore[arg-type]
        pr5 = fc.horizons["T+5"].dir
        pr20 = fc.horizons["T+20"].dir
        rows.append({
            "d": d, "p0": p0,
            "pr5": pr5, "gt5": gt5, "m5": m5, "hit5": pr5 == gt5,
            "pr20": pr20, "gt20": gt20, "m20": m20, "hit20": pr20 == gt20,
        })
        print(f"  {d}  price={p0:.2f} | T+5 预测 {pr5:<4} 实际 {gt5:<4}({m5:+.1f}%) "
              f"{'✅' if pr5==gt5 else '❌'} | T+20 预测 {pr20:<4} 实际 {gt20:<4}({m20:+.1f}%) "
              f"{'✅' if pr20==gt20 else '❌'}")
        # 学派账本接线：per-school + 内嵌真值块（ledger 可直接消费，无选择偏差）
        _emit_school_block(target, d, fc, gt5, gt20)

    valid = [r for r in rows if r["gt5"] != "?" and r["gt20"] != "?"]
    if not valid:
        print("\n无有效点（factual_rag 未返回价格）")
        return
    h5 = sum(r["hit5"] for r in valid)
    h20 = sum(r["hit20"] for r in valid)
    n = len(valid)
    tot = h5 + h20

    # 真实涨跌分布（判断 flat 阈值是否合理 + 是否平稳期）
    def _dist(key):
        c = {"up": 0, "down": 0, "flat": 0}
        for r in valid:
            c[r[key]] += 1
        return c

    print(f"\n========== {target} 平稳期连续命中率 ==========")
    print(f"有效月度点: {n}")
    print(f"T+5  命中: {h5}/{n} = {h5/n*100:.0f}%   真实分布 {_dist('gt5')}")
    print(f"T+20 命中: {h20}/{n} = {h20/n*100:.0f}%   真实分布 {_dist('gt20')}")
    print(f"合计 命中: {tot}/{n*2} = {tot/(n*2)*100:.0f}%")
    print(f"W3 ≥60%: {'✅ PASS' if tot/(n*2) >= 0.6 else '❌ FAIL'}")
    avg_abs5 = sum(abs(r["m5"]) for r in valid) / n
    avg_abs20 = sum(abs(r["m20"]) for r in valid) / n
    print(f"\n平均绝对涨跌幅: T+5 {avg_abs5:.2f}% / T+20 {avg_abs20:.2f}%  "
          f"(越小越平稳; 对照戏剧性事件常 >2%)")

    _fit_metrics(valid)
    _trend_scorecard(valid)
    return rows


_SIGN = {"up": 1, "flat": 0, "down": -1}

# 趋势 flat 带：窗口净涨跌幅绝对值 < 此值算 flat（窗越长容忍越大）
_TREND_FLAT = {3: 2.0, 6: 3.0}


def _trend_scorecard(valid: list[dict]) -> None:
    """考法 C · 压力趋势记分卡（路线 C / 16-ADR 的合法考法）。

    不考逐月小抖动（噪声，本就声明不预测），只考：
    **系统的结构压力立场，在足够长的窗口上，是否匹配实际净走势方向。**
    含诚实基线对照（11-ADR）：与"永远猜最常见方向"的笨基线比，
    系统只有**显著高于笨基线**才算真有压力识别力，否则只是趋势运气。
    """
    n = len(valid)
    prices = [r["p0"] for r in valid]
    # 系统每月的"压力立场"取 T+20 预测（结构/中期那一档）
    stance = [r["pr20"] for r in valid]
    actual_dirs = [r["gt20"] for r in valid]

    print(f"\n========== 考法 C · 压力趋势记分卡（{n} 月，路线C合法考法）==========")

    def _net_dir(p0, p1, flat_pct):
        if p0 == 0:
            return "?"
        pct = (p1 - p0) / p0 * 100.0
        return "flat" if abs(pct) < flat_pct else ("up" if pct > 0 else "down")

    for W in (3, 6):
        if n < W + 1:
            continue
        hits = tot = 0
        detail = []
        for i in range(n - W):
            seg_stance = stance[i:i + W]
            cnt: dict = {}
            for s in seg_stance:
                cnt[s] = cnt.get(s, 0) + 1
            sys_dir = max(cnt, key=cnt.get)
            act_dir = _net_dir(prices[i], prices[i + W], _TREND_FLAT[W])
            tot += 1
            ok = sys_dir == act_dir
            hits += ok
            detail.append(f"{valid[i]['d'][:7]}→+{W}m 系统{sys_dir}/实际{act_dir}{'✓' if ok else '✗'}")
        print(f"  滚动{W}月趋势: {hits}/{tot} = {hits/tot*100:.0f}%   "
              f"[{'  '.join(detail)}]")

    # 全程趋势
    whole = _net_dir(prices[0], prices[-1], 3.0)
    cnt = {}
    for s in stance:
        cnt[s] = cnt.get(s, 0) + 1
    sys_whole = max(cnt, key=cnt.get)
    print(f"  全程趋势  : 系统主立场 {sys_whole} / 实际净走势 {whole} "
          f"({prices[0]:.1f}→{prices[-1]:.1f}, {(prices[-1]-prices[0])/prices[0]*100:+.1f}%) "
          f"{'✓ 命中' if sys_whole==whole else '✗ 错'}")

    # 诚实基线：永远猜实际最常见方向（一个常数预测器能拿多少）
    acnt: dict = {}
    for a in actual_dirs:
        acnt[a] = acnt.get(a, 0) + 1
    base_dir = max(acnt, key=acnt.get)
    base_score = acnt[base_dir] / n
    sys_score = sum(1 for s, a in zip(stance, actual_dirs) if s == a) / n
    print(f"  诚实基线对照: 笨基线('永远猜{base_dir}') 月度命中 {base_score*100:.0f}% | "
          f"系统月度命中 {sys_score*100:.0f}% → "
          f"{'系统>基线, 有压力识别力' if sys_score > base_score + 1e-9 else '系统≤基线, 仅趋势运气/无额外技能'}")
    print("  解读: 压力仪表盘的合法主张是'中长窗口趋势方向', 不是逐月; "
          "但必须显著超过笨基线才算真技能")


def _fit_metrics(valid: list[dict]) -> None:
    """考法 B：曲线拟合记分卡（用户方法论 —— 单月二元太严苛，多看几个公平指标）。

    B1 严苛逐月二元   = 错噪声月与错大月同罚（最严苛，原始命中率）
    B2 幅度加权命中   = 命中按 |真实涨跌幅| 加权（噪声月几乎不计分，更公平）
    B3 方向序列相关 r = 预测方向序列 vs 真实序列的相关系数（曲线形状贴合度）
    B4 滚动3月趋势    = 每 3 月聚合后判方向（降噪 ≈ 线性/趋势拟合）
    """
    n = len(valid)
    print(f"\n========== 考法 B · 曲线拟合记分卡（{n} 月连续）==========")

    def block(pk, gk, mk, label):
        raw = sum(1 for r in valid if r[pk] == r[gk]) / n
        ws = sum(abs(r[mk]) for r in valid)
        wh = (sum(abs(r[mk]) for r in valid if r[pk] == r[gk]) / ws) if ws else 0.0
        xs = [_SIGN[r[pk]] for r in valid]
        ys = [_SIGN[r[gk]] for r in valid]
        mx, my = sum(xs) / n, sum(ys) / n
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        vx = sum((x - mx) ** 2 for x in xs) ** 0.5
        vy = sum((y - my) ** 2 for y in ys) ** 0.5
        corr = cov / (vx * vy) if vx and vy else 0.0
        h = t = 0
        for i in range(n - 2):
            seg = valid[i:i + 3]
            net = sum(r[mk] for r in seg)
            ad = "up" if net > 0.5 else ("down" if net < -0.5 else "flat")
            cnt: dict = {}
            for r in seg:
                cnt[r[pk]] = cnt.get(r[pk], 0) + 1
            t += 1
            h += (max(cnt, key=cnt.get) == ad)
        roll = h / t if t else 0.0
        print(f"  {label}: B1严苛 {raw*100:>3.0f}% | B2幅度加权 {wh*100:>3.0f}% | "
              f"B3方向相关 r={corr:+.2f} | B4滚动3月趋势 {roll*100:>3.0f}%")

    block("pr5", "gt5", "m5", "未来1周(T+5) ")
    block("pr20", "gt20", "m20", "未来1月(T+20)")
    print("  解读: r≈0 = 预测线与真实曲线无关联(只会一个方向); "
          "B2 仍 <60% = 即便只看大波动月也没及格")
    return


# ============================================================
# 考法 D · 长周期资产配置罗盘有效性（16-ADR §7.1）
# ============================================================
import re as _re

# 三态中性带（宽）：|净移动%| < 此值 = 中性（"无明确大方向"）
_COMPASS_NEUTRAL = {"T+30": 2.0, "T+90": 4.0}
_COMPASS_DAYS = {"T+30": 30, "T+90": 90}

# 不对称成本（对散户的真实伤害）：
#   抓对方向 / 该中性时说中性      = +1.0
#   说中性但实际有趋势(踏空,未伤)  =  0.0
#   说方向但实际中性(让散户瞎动)   = -0.5
#   说反方向(罗盘指反,主动害人)    = -1.0
def _compass_points(engine: str, truth: str) -> float:
    if engine == truth:
        return 1.0
    if engine == "中性":
        return 0.0
    if truth == "中性":
        return -0.5
    return -1.0  # 方向相反


_LINE_RE = _re.compile(
    r'(\d{4}-\d\d-\d\d)\s+price=([\d.]+).*?'
    r'T\+20 预测\s*(up|down|flat)\s*实际')


def _parse_log(path: str) -> list[tuple[str, float, str]]:
    """从已有连续回测 log 取 (date, price, engine_T+20_stance)。复用昂贵的 LLM 结果。"""
    out = []
    for ln in open(path):
        m = _LINE_RE.search(ln)
        if m:
            d, p, st = m.groups()
            out.append((d, float(p), st))
    return out


def _net_state(p0: float, p1: Optional[float], band: float) -> str:
    if p0 is None or p1 is None or p0 == 0:
        return "?"
    pct = (p1 - p0) / p0 * 100.0
    return "中性" if abs(pct) < band else ("看多" if pct > 0 else "看空")


_STANCE_MAP = {"up": "看多", "down": "看空", "flat": "中性"}


def compass_eval(logs: list[str], target: str = "USD/JPY") -> None:
    """考法 D：用已有 log 的 engine 立场 + factual_rag 补 T+30/T+90 真实价，
    诚实评估"长周期资产配置罗盘"价值。零 LLM 成本（复用历史预测）。"""
    pvar = _PRICE_VAR[target]
    all_rows: list[dict] = []
    per_period: list[tuple[str, list[dict]]] = []

    for lg in logs:
        pts = _parse_log(lg)
        if not pts:
            print(f"  [skip] {lg} 无可解析点")
            continue
        rows = []
        for d, p0, st in pts:
            row = {"d": d, "p0": p0, "engine": _STANCE_MAP.get(st, "中性")}
            for H in ("T+30", "T+90"):
                fr = _fr_state(_shift(d, _COMPASS_DAYS[H]))
                p1 = _price(fr, pvar) if fr else None
                row[f"truth_{H}"] = _net_state(p0, p1, _COMPASS_NEUTRAL[H])
            rows.append(row)
        per_period.append((f"{pts[0][0]}→{pts[-1][0]} ({len(rows)}月)", rows))
        all_rows += rows

    if not all_rows:
        print("无数据")
        return

    print(f"\n{'='*64}")
    print(f"考法 D · 长周期资产配置罗盘有效性  [{target}]  共 {len(all_rows)} 月度点")
    print(f"{'='*64}")
    print("三态: 看多/看空/中性  |  中性带 T+30<2% T+90<4%  |  engine立场=T+20预测")
    print("成本: 抓对/该中性说中性 +1 | 说中性实际有势 0 | 说势实际中性 -0.5 | 指反 -1\n")

    def score(rows, who, pick):
        for H in ("T+30", "T+90"):
            tot = 0.0
            valid = [r for r in rows if r[f"truth_{H}"] != "?"]
            if not valid:
                continue
            for r in valid:
                tot += _compass_points(pick(r, H), r[f"truth_{H}"])
            avg = tot / len(valid)
            # 映射到 0-100 罗盘分（-1→0, +1→100）
            sc = (avg + 1) / 2 * 100
            yield H, sc, len(valid)

    def base_neutral(r, H): return "中性"
    def base_engine(r, H): return r["engine"]
    # 停摆钟 = 永远猜该数据集真实最常见方向
    def _dominant(rows, H):
        c: dict = {}
        for r in rows:
            t = r[f"truth_{H}"]
            if t != "?":
                c[t] = c.get(t, 0) + 1
        return max(c, key=c.get) if c else "中性"

    dom = {H: _dominant(all_rows, H) for H in ("T+30", "T+90")}
    def base_clock(r, H): return dom[H]

    print(f"{'对象':<22}{'T+30 罗盘分':>14}{'T+90 罗盘分':>14}")
    print("-" * 52)
    for label, pick in [("🧭 系统(engine)", base_engine),
                         ("基线·永远中性", base_neutral),
                         ("基线·停摆钟", base_clock)]:
        cells = {H: f"{sc:.0f}/100 (n={k})" for H, sc, k in score(all_rows, label, pick)}
        print(f"{label:<22}{cells.get('T+30',''):>14}{cells.get('T+90',''):>14}")
    print(f"  (停摆钟此数据集主方向: T+30={dom['T+30']} T+90={dom['T+90']})")

    # 真值分布 + 判决
    print("\n真实三态分布:")
    for H in ("T+30", "T+90"):
        c: dict = {"看多": 0, "看空": 0, "中性": 0}
        for r in all_rows:
            if r[f"truth_{H}"] in c:
                c[r[f"truth_{H}"]] += 1
        print(f"  {H}: {c}")

    eng = {H: sc for H, sc, _ in score(all_rows, "e", base_engine)}
    neu = {H: sc for H, sc, _ in score(all_rows, "n", base_neutral)}
    clk = {H: sc for H, sc, _ in score(all_rows, "c", base_clock)}
    print("\n判决（罗盘只有同时显著优于'永远中性'与'停摆钟'才算有价值）:")
    for H in ("T+30", "T+90"):
        if H not in eng:
            continue
        win = eng[H] > neu[H] + 3 and eng[H] > clk[H] + 3
        print(f"  {H}: 系统 {eng[H]:.0f} vs 永远中性 {neu[H]:.0f} vs 停摆钟 {clk[H]:.0f}"
              f"  → {'✅ 罗盘有价值' if win else '❌ 未显著优于基线 = 罗盘暂无价值'}")
    print("\n分周期明细:")
    for label, rows in per_period:
        e = {H: sc for H, sc, _ in score(rows, "e", base_engine)}
        print(f"  {label}: 系统 T+30={e.get('T+30',0):.0f} T+90={e.get('T+90',0):.0f}")


# ============================================================
# 事前催化剂探测器（16-ADR §7.5）—— 只用 T 时点可得 + 历史连续可得信号
# 严禁事后价格反推；严禁手搓快照；严禁薄事件流
# ============================================================
# 触发阈值（保守，可调；阈值本身是事前设定，非按结果调）
_CAT_GPR_MULT = 1.30      # GPR 30日均 > 滚动12月均 ×1.3 → 地缘催化剂
_CAT_RATE_DPP = 0.50      # 政策利率 vs 6月前 |Δ| ≥ 0.5pp → 货币周期催化剂
_CAT_CPI_DPP = 1.00       # CPI yoy vs 3月前 |Δ| ≥ 1.0pp → 通胀加速催化剂


def _catalyst_asof(date: str) -> tuple[bool, list[str]]:
    """事前催化剂判定：仅用 date 当时及之前可得的连续变量。返回 (是否触发, 原因)。"""
    reasons: list[str] = []
    fr0 = _fr_state(date)
    if fr0 is None:
        return False, ["no_data"]

    # 1) GPR 飙升 vs 滚动 12 月基线（取 date / -6m / -12m 三点估基线）
    g0 = _v(fr0, "level_0", "gpr_30d_avg")
    base_pts = []
    for off in (180, 365):
        frb = _fr_state(_shift(date, -off))
        gb = _v(frb, "level_0", "gpr_30d_avg") if frb else None
        if gb is not None:
            base_pts.append(gb)
    if g0 is not None and base_pts:
        base = sum(base_pts) / len(base_pts)
        if base > 0 and g0 > base * _CAT_GPR_MULT:
            reasons.append(f"GPR飙升({g0:.0f}>{base:.0f}×{_CAT_GPR_MULT})")

    # 2) 政策利率周期：vs 6 月前
    fr6 = _fr_state(_shift(date, -180))
    r0 = _v(fr0, "level_1", "fed_funds_target_upper") or _v(fr0, "level_1", "fed_funds_rate")
    r6 = (_v(fr6, "level_1", "fed_funds_target_upper") or _v(fr6, "level_1", "fed_funds_rate")) if fr6 else None
    if r0 is not None and r6 is not None and abs(r0 - r6) >= _CAT_RATE_DPP:
        reasons.append(f"政策利率周期(Δ6m={r0 - r6:+.2f}pp)")

    # 3) 通胀加速度：vs 3 月前
    fr3 = _fr_state(_shift(date, -90))
    c0 = _v(fr0, "level_0", "us_cpi_yoy")
    c3 = _v(fr3, "level_0", "us_cpi_yoy") if fr3 else None
    if c0 is not None and c3 is not None and abs(c0 - c3) >= _CAT_CPI_DPP:
        reasons.append(f"通胀加速(Δ3m={c0 - c3:+.1f}pp)")

    return (len(reasons) > 0), reasons


def compass_eval_event(logs: list[str], target: str = "USD/JPY") -> None:
    """考法 E：事件触发型罗盘诚实评估（复用已有 log 预测，零 LLM）。

    系统按事前催化剂规则自行决定何时开口：
      - 开口（催化剂触发）→ 用 engine 立场算考法D分
      - 沉默（无催化剂）  → 记"沉默"（≈中性，等价 76 基线那套不对称记分）
    强制反作弊报告：开口率 + 开口/沉默两组真实 move 分布。
    """
    pvar = _PRICE_VAR[target]
    rows: list[dict] = []
    for lg in logs:
        for d, p0, st in _parse_log(lg):
            fired, why = _catalyst_asof(d)
            row = {"d": d, "p0": p0, "engine": _STANCE_MAP.get(st, "中性"),
                   "fired": fired, "why": ";".join(why)}
            for H in ("T+30", "T+90"):
                fr = _fr_state(_shift(d, _COMPASS_DAYS[H]))
                row[f"truth_{H}"] = _net_state(p0, _price(fr, pvar) if fr else None,
                                               _COMPASS_NEUTRAL[H])
            rows.append(row)

    n = len(rows)
    fired = [r for r in rows if r["fired"]]
    silent = [r for r in rows if not r["fired"]]
    print(f"\n{'='*64}")
    print(f"考法 E · 事件触发型罗盘（{target}，{n} 月，零 LLM 复用预测）")
    print(f"{'='*64}")
    print(f"开口率: {len(fired)}/{n} = {len(fired)/n*100:.0f}%  "
          f"(沉默 {len(silent)}/{n})")

    # 反作弊：两组真实 move 分布（开口组应更偏'有方向'）
    def dist(grp, H):
        c = {"看多": 0, "看空": 0, "中性": 0}
        for r in grp:
            t = r[f"truth_{H}"]
            if t in c:
                c[t] += 1
        tot = sum(c.values()) or 1
        directional = (c["看多"] + c["看空"]) / tot * 100
        return c, directional

    print("\n反作弊·两组真实行情分布（开口组该明显更'有方向'，否则规则无筛选力）:")
    for H in ("T+30", "T+90"):
        cf, df = dist(fired, H)
        cs, ds = dist(silent, H)
        print(f"  {H}: 开口 {cf} 有方向占比{df:.0f}%  |  沉默 {cs} 有方向占比{ds:.0f}%"
              f"  → {'✅ 规则有筛选力' if df > ds + 8 else '❌ 两组差不多=规则无筛选力'}")

    # 考法D 记分：开口=engine立场；沉默=中性
    def pts_row(r, H):
        e = r["engine"] if r["fired"] else "中性"
        return _compass_points(e, r[f"truth_{H}"])

    print("\n考法D 记分（开口用engine / 沉默记中性）vs 基线:")
    for H in ("T+30", "T+90"):
        valid = [r for r in rows if r[f"truth_{H}"] != "?"]
        if not valid:
            continue
        sys_avg = sum(pts_row(r, H) for r in valid) / len(valid)
        neu_avg = sum(_compass_points("中性", r[f"truth_{H}"]) for r in valid) / len(valid)
        sys_s = (sys_avg + 1) / 2 * 100
        neu_s = (neu_avg + 1) / 2 * 100
        # 仅看开口子集的方向准确率（剔除中性真值）
        fsub = [r for r in fired if r[f"truth_{H}"] in ("看多", "看空")]
        dir_hit = (sum(1 for r in fsub if r["engine"] == r[f"truth_{H}"]) / len(fsub) * 100
                   if fsub else 0.0)
        win = sys_s > neu_s + 3
        print(f"  {H}: 事件触发系统 {sys_s:.0f} vs 永远沉默/中性 {neu_s:.0f}"
              f"  {'✅ 超过基线' if win else '❌ 未超基线'}"
              f"  | 开口子集方向命中 {dir_hit:.0f}% (n={len(fsub)})")
    print("\n判决: 需同时(1)开口组真实更有方向 (2)系统分>永远沉默 才算事件触发型站得住")
