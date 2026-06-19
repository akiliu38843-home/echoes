"""考法 F · 脆弱性预警校准记分卡（structural_prudential agent 的诚实考场）。

agent 的产品主张是一个**概率**：「未来 H 月内出现 ≥X% 大异动的概率 ≈ b%（常态 ≈ a%）」。
所以它不能用方向命中率考，必须用**概率校准 + 相对常态基率的技能**考。本模块 = 这套考场，
预测端**可插拔**：今天只有"纯价格代理"(已证伪，作 null) 与两个笨基线；RAG 的 P1
(NFCI/VIX/信贷) 一注册，`RagFragilityComposite` 立即可跑——即插即测。

诚实纪律（§4 + [[feedback-honest-failure-over-patching]]）：
- HOLDOUT(>2013) 是头条成绩；TRAIN 只用于定阈，明确标"仅参考"
- 永远并列两个笨基线："永远喊危险"(提升≡0) 与 "永远不喊"(≡基率) → 信号须显著>0
- 概率预测算 Brier 技能分 (BSS)：只会吐基率常数者 BSS≈0，必须超过它
- 前瞻窗重叠→自相关抬高显著性：报有效N + 非重叠子样本交叉验
- RAG 变量缺失时预测端**诚实弃权**，绝不编造顶替（沿用 1971/1973 留白精神）
"""
from __future__ import annotations

import datetime as _dt
import math
import statistics as _stat
from typing import Callable, Optional, Protocol

import requests

from hindcast.vol_paradox import (
    FACTUAL_RAG, _NOPROXY, THRESH, HORIZONS, TRAIN_END, fetch_series,
)


# ──────────────────────────────────────────────────────────────────────
# 被预测对象：未来 H 月内峰谷振幅 ≥ 定稿阈值（大涨或大跌任一）
# ──────────────────────────────────────────────────────────────────────
def make_outcome(series: dict[str, float]):
    weeks = sorted(series)
    px = [series[w] for w in weeks]
    n = len(weeks)
    wdate = [_dt.date.fromisoformat(w) for w in weeks]

    def outcome(i: int, months: int) -> Optional[bool]:
        end = wdate[i] + _dt.timedelta(days=int(months * 30.44))
        fwd = [px[j] for j in range(i + 1, n) if wdate[j] <= end]
        if len(fwd) < max(4, months):
            return None
        p0 = px[i]
        return ((p0 - min(fwd)) / p0 * 100.0 >= THRESH[months]) or \
               ((max(fwd) - p0) / p0 * 100.0 >= THRESH[months])

    # 月度决策点（每 ~4 周）
    dec = [i for i in range(n) if i % 4 == 0]
    return weeks, px, dec, outcome


# ──────────────────────────────────────────────────────────────────────
# 预测端协议（可插拔）：score(asof)->[0,1] 脆弱概率；None=诚实弃权
# ──────────────────────────────────────────────────────────────────────
class Predictor(Protocol):
    name: str
    def ready(self) -> tuple[bool, str]: ...
    def score(self, asof: str) -> Optional[float]: ...


def _fr_val(date: str, level: str, key: str) -> Optional[float]:
    try:
        r = requests.get(f"{FACTUAL_RAG}/state/asof", params={"date": date},
                          timeout=8, proxies=_NOPROXY)
        if r.status_code == 200:
            node = r.json().get(level, {}).get(key)
            return node.get("value") if isinstance(node, dict) else None
    except Exception:
        return None
    return None


class AlwaysDanger:
    name = "笨基线·永远喊危险"
    def ready(self): return True, ""
    def score(self, asof): return 1.0


class NeverDanger:
    name = "笨基线·永远不喊"
    def ready(self): return True, ""
    def score(self, asof): return 0.0


class PriceVolGapProxy:
    """已证伪的纯价格波动率缺口（17-ADR §5c.2，台账#11）。保留作 null/回归对照。"""
    name = "纯价格波动率缺口(已证伪,作null)"
    def __init__(self, series: dict[str, float]):
        wk = sorted(series)
        px = [series[w] for w in wk]
        lr = [float("nan")] + [math.log(px[i] / px[i-1]) for i in range(1, len(px))]
        TRAIL, BASE = 26, 260
        rv = [float("nan")] * len(wk)
        for i in range(len(wk)):
            if i >= TRAIL:
                seg = lr[i-TRAIL+1:i+1]
                rv[i] = _stat.pstdev(seg) * math.sqrt(52.0)
        self._z = {}
        for i in range(len(wk)):
            hist = [rv[j] for j in range(max(0, i-BASE), i) if not math.isnan(rv[j])]
            if not math.isnan(rv[i]) and len(hist) >= 52:
                mu = _stat.mean(hist); sd = _stat.pstdev(hist) or 1e-9
                # 低波动 → 高"脆弱"概率：把 z 经 logistic 映射(注：方向取负=刻意按悖论假设，
                # 已知会失败，正是要让考场暴露它，不是补丁)
                self._z[wk[i]] = 1.0 / (1.0 + math.exp((rv[i]-mu)/sd))
    def ready(self): return True, ""
    def score(self, asof): return self._z.get(asof)


class RagFragilityComposite:
    """RAG P1/P2 脆弱性合成（即插即测）。NFCI + VIX + 信用利差 + 信贷/GDP 缺口 z 合成。
    任一核心变量 RAG 未注册 → 整体诚实弃权（不编造），并报缺哪个。"""
    name = "RAG脆弱性合成(等P1数据)"
    REQ = [("level_0", "us_nfci"), ("level_2", "vix_index"),
           ("level_2", "us_hy_oas"), ("level_0", "us_private_credit_to_gdp")]
    def ready(self):
        probe = "2016-06-15"
        miss = [k for lv, k in self.REQ if _fr_val(probe, lv, k) is None]
        if miss:
            return False, f"RAG 未就绪，缺: {', '.join(miss)}"
        return True, "全部就绪"
    def score(self, asof):
        # 真实合成逻辑等 P1 落地后实现；未就绪 → 诚实 None（弃权）
        ok, _ = self.ready()
        if not ok:
            return None
        nfci = _fr_val(asof, "level_0", "us_nfci")
        vix = _fr_val(asof, "level_2", "vix_index")
        hy = _fr_val(asof, "level_2", "us_hy_oas")
        if None in (nfci, vix, hy):
            return None
        # 占位合成：NFCI 越高(紧/风险) + 利差异常压缩 + VIX 异常低 → 脆弱↑
        # 真版需历史 z 标准化(同样仅用过去信息)，待 P1 数据到位实装
        return None


# ──────────────────────────────────────────────────────────────────────
# 记分
# ──────────────────────────────────────────────────────────────────────
def _bss(scores: list[float], ys: list[int], base: float) -> float:
    if not scores:
        return float("nan")
    bs = sum((s - y) ** 2 for s, y in zip(scores, ys)) / len(scores)
    bs_ref = base * (1 - base) or 1e-9
    return 1 - bs / bs_ref


def score_predictor(pred: Predictor, series: dict[str, float]) -> None:
    weeks, px, dec, outcome = make_outcome(series)
    print("=" * 68)
    print(f"考法 F · {pred.name}")
    print("=" * 68)
    ok, msg = pred.ready()
    if not ok:
        print(f"⚠️ 预测端诚实弃权：{msg}")
        print("   → 考场已就绪；RAG 注册 P1 变量后本预测端即插即测。")
        return

    # 用 TRAIN 段 score 分布的上三分位作"开口"阈值（§4：只用 train 定）
    tr_scores = sorted(s for i in dec
                       if weeks[i] <= TRAIN_END
                       and (s := pred.score(weeks[i])) is not None)
    if not tr_scores:
        print("TRAIN 段无有效预测分，无法定阈"); return
    FIRE = tr_scores[2 * len(tr_scores) // 3]
    print(f"[§4] 开口阈值 score ≥ {FIRE:.3f}（仅 TRAIN≤{TRAIN_END} 上三分位定）\n")

    for seg, keep in (("TRAIN(≤2013,定阈,仅参考)", lambda w: w <= TRAIN_END),
                      ("HOLDOUT(>2013,真考场)", lambda w: w > TRAIN_END)):
        print(f"───── {seg} ─────")
        for H in HORIZONS:
            rows = []
            for i in dec:
                if not keep(weeks[i]):
                    continue
                s = pred.score(weeks[i]); y = outcome(i, H)
                if s is None or y is None:
                    continue
                rows.append((weeks[i], s, 1 if y else 0))
            if not rows:
                continue
            n = len(rows)
            base = sum(y for _, _, y in rows) / n
            fired = [(w, s, y) for w, s, y in rows if s >= FIRE]
            cond = (sum(y for _, _, y in fired) / len(fired)) if fired else float("nan")
            lift = (cond - base) if fired else float("nan")
            bss = _bss([s for _, s, _ in rows], [y for _, _, y in rows], base)
            # 非重叠子样本（决策点间隔≥H月）交叉验
            no, last = [], None
            for w, s, y in rows:
                d = _dt.date.fromisoformat(w)
                if last is None or (d - last).days >= H * 30:
                    no.append((s, y)); last = d
            nob = (sum(y for _, y in no) / len(no)) if no else float("nan")
            nofire = [y for s, y in no if s >= FIRE]
            nolift = (sum(nofire) / len(nofire) - nob) if nofire else float("nan")
            print(f"  H={H:>2}月 阈≥{THRESH[H]:.0f}% | 基率 a={base*100:4.0f}% "
                  f"开口后 b={cond*100:4.0f}% 提升{lift*100:+5.1f}pp (开口N={len(fired)}/{n}) "
                  f"| BSS={bss:+.2f} | 非重叠提升{nolift*100:+5.1f}pp(N={len(no)})")
        print("  对照: 永远喊危险 提升≡0 / 永远不喊≡基率 → 须 HOLDOUT 显著>0 且 BSS>0 才算真技能")
    print("\n诚实边界: 单标的USD/JPY; 前瞻窗重叠(已附非重叠交叉验); N小; "
          "结论作'有无技能'非可交易概率。预测端升级靠 RAG P1。")


def run_kaofa_f(which: str = "all") -> None:
    series = fetch_series()
    if len(series) < 300:
        print("数据不足（factual_rag 在线？）"); return
    cands = {
        "never": NeverDanger(), "always": AlwaysDanger(),
        "proxy": PriceVolGapProxy(series), "rag": RagFragilityComposite(),
    }
    todo = cands.values() if which == "all" else [cands[which]]
    for p in todo:
        score_predictor(p, series)
        print()


if __name__ == "__main__":
    import sys
    run_kaofa_f(sys.argv[1] if len(sys.argv) > 1 else "all")
