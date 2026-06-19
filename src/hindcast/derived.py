"""派生预测（Phase 4a）—— 从已有 target 预测确定性组合，无新 prompt / 学派。

第一个派生 target：**2s10s 利差**（= US 10Y − US 2Y）。

设计原则（14-ROADMAP §4a）:
  - 不引入新 LLM prompt / 学派立场——纯复用 predict_yield(US_2Y) + predict_yield(US_10Y)
  - 方向 = 收益率曲线斜率变化:
      steepen (up)   = 曲线变陡（10Y 相对 2Y 上行）
      flatten (down) = 曲线变平/倒挂（2Y 相对 10Y 上行）
      flat           = 斜率基本不变
  - GT 从 YIELD_GROUND_TRUTH 确定性派生: Δspread = Δ10Y_bps − Δ2Y_bps
  - 服务于 Phase 4d 衰退概率（2s10s 倒挂是经典衰退领先指标）
"""

from __future__ import annotations

from typing import Literal, Optional

from openai import OpenAI
from pydantic import BaseModel

from hindcast.state import StructuralState
from hindcast.treasury_yield import predict_yield, YieldForecast


# 斜率变化阈值（bps）：|Δspread| < 此值 → flat
SLOPE_FLAT_THRESHOLD_BPS = 8.0
# 当某 horizon 学派给方向但缺 range_bps 时的兜底幅度（bps）
DIR_FALLBACK_BPS = 15.0

_DIR_SIGN = {"up": 1.0, "down": -1.0, "flat": 0.0}


class SpreadHorizon(BaseModel):
    dir: Literal["up", "down", "flat"]      # up=steepen, down=flatten, flat=斜率不变
    expected_2y_bps: float                  # 4 学派平均预期 Δ2Y (signed)
    expected_10y_bps: float                 # 4 学派平均预期 Δ10Y (signed)
    expected_spread_bps: float              # = expected_10y_bps − expected_2y_bps


class SpreadForecast(BaseModel):
    as_of: str
    label: str
    target: str = "US_2s10s"
    current_spread_bps: float | None = None     # 当前 10Y−2Y 水平 (bps)
    horizons: dict[str, SpreadHorizon]
    # 引用的两个上游预测（审计用）
    yield_2y: YieldForecast
    yield_10y: YieldForecast


def _expected_signed_bps(forecast: YieldForecast, horizon: str) -> float:
    """4 学派平均的 signed Δyield（bps）。

    符号取自 dir（权威字段），幅度取 range_bps 绝对值均值；
    若学派给了方向但 range_bps 缺失（默认 [0,0]）→ 用 DIR_FALLBACK_BPS 兜底，
    避免"有方向无幅度"被当成 0。
    """
    vals: list[float] = []
    for v in forecast.verdicts:
        if v._failed:
            continue
        yh = v.verdict.get(horizon)
        if yh is None:
            continue
        sign = _DIR_SIGN.get(yh.dir, 0.0)
        if sign == 0.0:
            vals.append(0.0)
            continue
        lo, hi = (yh.range_bps + [0.0, 0.0])[:2]
        mag = (abs(lo) + abs(hi)) / 2.0
        if mag == 0.0:
            mag = DIR_FALLBACK_BPS
        vals.append(sign * mag)
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def _classify_spread(delta_spread_bps: float) -> Literal["up", "down", "flat"]:
    if delta_spread_bps > SLOPE_FLAT_THRESHOLD_BPS:
        return "up"        # steepen
    if delta_spread_bps < -SLOPE_FLAT_THRESHOLD_BPS:
        return "down"      # flatten / invert
    return "flat"


def predict_2s10s(
    state: StructuralState,
    horizons: list[str] | None = None,
    client: OpenAI | None = None,
) -> SpreadForecast:
    """复用 2Y / 10Y 预测，确定性派生 2s10s 斜率方向。"""
    from hindcast.llm import get_client
    horizons = horizons or ["T+5", "T+20"]
    client = client or get_client()

    f2y = predict_yield(state, "US_2Y", horizons=horizons, client=client)
    f10y = predict_yield(state, "US_10Y", horizons=horizons, client=client)

    spread_h: dict[str, SpreadHorizon] = {}
    for h in horizons:
        e2 = _expected_signed_bps(f2y, h)
        e10 = _expected_signed_bps(f10y, h)
        d_spread = e10 - e2
        spread_h[h] = SpreadHorizon(
            dir=_classify_spread(d_spread),
            expected_2y_bps=round(e2, 1),
            expected_10y_bps=round(e10, 1),
            expected_spread_bps=round(d_spread, 1),
        )

    macro = state.macro
    cur = None
    if macro and macro.treasury_10y_yield is not None and macro.treasury_2y_yield is not None:
        cur = round((macro.treasury_10y_yield - macro.treasury_2y_yield) * 100.0, 1)

    return SpreadForecast(
        as_of=state.as_of, label=state.label,
        current_spread_bps=cur,
        horizons=spread_h,
        yield_2y=f2y, yield_10y=f10y,
    )


def derive_2s10s_gt(as_of: str) -> dict[str, dict]:
    """从 YIELD_GROUND_TRUTH 确定性派生 2s10s GT。

    Δspread_bps = Δ10Y.actual_bps − Δ2Y.actual_bps
    方向用与预测相同的 ±SLOPE_FLAT_THRESHOLD_BPS 阈值。
    """
    from hindcast.data.ground_truth import YIELD_GROUND_TRUTH
    point = YIELD_GROUND_TRUTH.get(as_of)
    if not point or "US_2Y" not in point or "US_10Y" not in point:
        return {}
    out: dict[str, dict] = {}
    for h in ("T+5", "T+20"):
        g2 = point["US_2Y"].get(h)
        g10 = point["US_10Y"].get(h)
        if g2 is None or g10 is None:
            continue
        d = g10["actual_bps"] - g2["actual_bps"]
        out[h] = {"dir": _classify_spread(d), "actual_bps": d}
    return out


def run_2s10s_backtest(snapshots=None):
    from hindcast.data import ALL_SNAPSHOTS
    snapshots = snapshots or [s for s in ALL_SNAPSHOTS if s.macro is not None]
    results = []
    for snap in snapshots:
        gt = derive_2s10s_gt(snap.as_of)
        if not gt:
            print(f"\n========== {snap.label} ({snap.as_of}) — 跳过（无 2Y/10Y GT 派生）==========")
            continue
        print(f"\n========== {snap.label} ({snap.as_of}) [US_2s10s] ==========")
        fc = predict_2s10s(snap)
        for h in ("T+5", "T+20"):
            sh = fc.horizons[h]
            print(f"  {h}: {sh.dir:<5} (Δ2Y {sh.expected_2y_bps:+.0f} / Δ10Y {sh.expected_10y_bps:+.0f} → Δspread {sh.expected_spread_bps:+.0f} bps)")
        hit_t5 = fc.horizons["T+5"].dir == gt.get("T+5", {}).get("dir")
        hit_t20 = fc.horizons["T+20"].dir == gt.get("T+20", {}).get("dir")
        results.append({"label": snap.label, "fc": fc, "gt": gt, "hit_t5": hit_t5, "hit_t20": hit_t20})

    print(f"\n\n========== US 2s10s 利差 命中率（派生 target, 无新 prompt）==========")
    print(f"{'时点':<32} {'T+5':<8} {'T+5 GT':<8} {'hit':<5} {'T+20':<9} {'T+20 GT':<9} {'hit'}")
    print("-" * 96)
    hits_t5, hits_t20, valid = 0, 0, 0
    for r in results:
        valid += 1
        if r["hit_t5"]: hits_t5 += 1
        if r["hit_t20"]: hits_t20 += 1
        m5 = "✅" if r["hit_t5"] else "❌"
        m20 = "✅" if r["hit_t20"] else "❌"
        g5 = r["gt"].get("T+5", {}).get("dir", "?")
        g20 = r["gt"].get("T+20", {}).get("dir", "?")
        print(f"{r['label']:<32} {r['fc'].horizons['T+5'].dir:<8} {g5:<8} {m5:<5} {r['fc'].horizons['T+20'].dir:<9} {g20:<9} {m20}")
    print("-" * 96)
    if valid:
        total = hits_t5 + hits_t20
        print(f"T+5  命中率: {hits_t5}/{valid} = {hits_t5/valid*100:.0f}%")
        print(f"T+20 命中率: {hits_t20}/{valid} = {hits_t20/valid*100:.0f}%")
        print(f"合计 命中率: {total}/{valid*2} = {total/(valid*2)*100:.0f}%")
        print(f"W3 hard gate ≥60%: {'✅ PASS' if total/(valid*2) >= 0.6 else '❌ FAIL'}")
        print(f"\n注: steepen=up(曲线变陡) / flatten=down(变平/倒挂) / flat=斜率不变")
    return results
