"""红队 2026-05-16 R3–R6 + §1 Layer2 点名的标准方法，numpy/scipy 正确实现。

对应关系（红队条款 → 本模块函数）：
  R3 长窗推断/手搓非重叠 → moving_block_bootstrap_ci（Künsch 1989 移动块自助）
                          + hac_mean_tstat（Newey–West 1987 HAC，修 Valkanov 过度拒绝）
  R4 BSS 头条不稳        → pr_auc（不平衡用 AUC-PR）+ reliability_bins（带二项一致带）
                          + log_loss；brier/brier_skill_score 降为次要、显式标注
  R5 振幅随机游走下上偏  → amplitude_vs_null（并排 IID / 随机游走 null 带）
  R6 自创指标            → one_sided_hp_credit_gap（BIS 信贷-GDP 缺口，单边 HP λ=400000）
  §1 Layer2 方向技能     → pesaran_timmermann 1992 / diebold_mariano 1995（含 HLN 小样本校正）
                          / clark_west 2007（嵌套 OOS）

所有函数：纯 numpy/scipy、无数据 I/O、无副作用。仅量具，不产可计数产品结论。
"""

from __future__ import annotations

import numpy as np
from scipy import stats


# ───────────────────────── R3：块自助 + HAC ─────────────────────────


def _nw_lag(n: int) -> int:
    """Newey–West 自动滞后：floor(4 (n/100)^(2/9))，至少 1。"""
    return max(1, int(np.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))))


def hac_mean_tstat(x: np.ndarray, lags: int | None = None) -> dict:
    """样本均值的 Newey–West HAC t 检验（Bartlett 核）。

    修红队 R3 / Valkanov 2003：自相关下朴素 t 过度拒绝。返回长跑方差与 HAC t。
    """
    x = np.asarray(x, float)
    n = x.size
    if n < 3:
        return {"mean": float(np.mean(x)) if n else np.nan, "se": np.nan,
                "t": np.nan, "p": np.nan, "lags": 0, "n": n}
    L = _nw_lag(n) if lags is None else int(lags)
    xc = x - x.mean()
    g0 = np.dot(xc, xc) / n
    lrv = g0
    for k in range(1, min(L, n - 1) + 1):
        gk = np.dot(xc[k:], xc[:-k]) / n
        w = 1.0 - k / (L + 1.0)  # Bartlett
        lrv += 2.0 * w * gk
    lrv = max(lrv, 1e-18)
    se = np.sqrt(lrv / n)
    t = x.mean() / se
    p = 2.0 * stats.norm.sf(abs(t))
    return {"mean": float(x.mean()), "se": float(se), "t": float(t),
            "p": float(p), "lags": L, "n": n}


def moving_block_bootstrap_ci(
    x: np.ndarray,
    stat=np.mean,
    block: int | None = None,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> dict:
    """移动块自助 CI（Künsch 1989）——重叠/自相关下正确，替手搓非重叠。

    block 默认 ~ n^(1/3)。返回点估计 + 百分位 CI + 有效独立块数（功效线索）。
    """
    x = np.asarray(x, float)
    n = x.size
    if n < 4:
        s = float(stat(x)) if n else np.nan
        return {"stat": s, "lo": np.nan, "hi": np.nan, "n": n,
                "block": 0, "n_blocks_eff": 0}
    L = max(2, int(round(n ** (1.0 / 3.0)))) if block is None else int(block)
    L = min(L, n)
    rng = np.random.default_rng(seed)
    n_starts = n - L + 1
    k = int(np.ceil(n / L))
    boots = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, n_starts, size=k)
        samp = np.concatenate([x[s:s + L] for s in starts])[:n]
        boots[b] = stat(samp)
    lo, hi = np.percentile(boots, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {"stat": float(stat(x)), "lo": float(lo), "hi": float(hi),
            "n": n, "block": L, "n_blocks_eff": int(np.floor(n / L))}


# ───────────────────── R4：AUC-PR / 可靠性 / log-loss ─────────────────────


def pr_auc(prob: np.ndarray, y: np.ndarray) -> float:
    """Average Precision（PR 曲线下面积）——稀有事件不平衡下替 BSS 头条。"""
    prob = np.asarray(prob, float)
    y = np.asarray(y, int)
    if y.sum() == 0:
        return float("nan")
    order = np.argsort(-prob, kind="mergesort")
    y = y[order]
    tp = np.cumsum(y)
    fp = np.cumsum(1 - y)
    precision = tp / np.maximum(tp + fp, 1)
    recall = tp / y.sum()
    rec_prev = np.concatenate([[0.0], recall[:-1]])
    return float(np.sum((recall - rec_prev) * precision))


def brier(prob: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((np.asarray(prob, float) - np.asarray(y, float)) ** 2))


def brier_skill_score(prob, y, base: float | None = None) -> dict:
    """BSS（次要指标，红队 R4：稀有小 N 不稳、一个事件翻号——勿作头条）。"""
    y = np.asarray(y, float)
    base = float(y.mean()) if base is None else float(base)
    ref = base * (1 - base)
    bss = np.nan if ref <= 0 else 1.0 - brier(prob, y) / ref
    return {"bss": float(bss) if ref > 0 else np.nan, "base_rate": base,
            "_warning": "BSS 次要：稀有事件小 N 不稳，头条用 pr_auc/log_loss"}


def log_loss(prob: np.ndarray, y: np.ndarray, eps: float = 1e-15) -> float:
    p = np.clip(np.asarray(prob, float), eps, 1 - eps)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def reliability_bins(prob, y, n_bins: int = 10) -> list:
    """可靠性图分箱 + 完美校准下的二项 95% 一致带（Bröcker–Smith 精神的简版，已标注）。"""
    prob = np.asarray(prob, float)
    y = np.asarray(y, int)
    edges = np.linspace(0, 1, n_bins + 1)
    out = []
    for i in range(n_bins):
        m = (prob >= edges[i]) & (prob < edges[i + 1] if i < n_bins - 1
                                  else prob <= edges[i + 1])
        c = int(m.sum())
        if c == 0:
            continue
        p_mean = float(prob[m].mean())
        obs = float(y[m].mean())
        lo = stats.binom.ppf(0.025, c, p_mean) / c
        hi = stats.binom.ppf(0.975, c, p_mean) / c
        out.append({"bin": (float(edges[i]), float(edges[i + 1])),
                     "p_pred": p_mean, "freq_obs": obs, "n": c,
                     "band95": (float(lo), float(hi)),
                     "in_band": bool(lo <= obs <= hi)})
    return out


# ───────────────────── R5：振幅 vs IID / 随机游走 null ─────────────────────


def amplitude_vs_null(
    series: np.ndarray,
    stat_fn=lambda s: float(np.max(s) - np.min(s)),
    null: str = "rw",
    n_sim: int = 2000,
    seed: int = 0,
) -> dict:
    """观测振幅统计量 vs 同长 IID / 随机游走 null 带（红队 R5）。

    峰谷振幅即便纯随机游走下也机械上偏；只有超出 null 带的部分可解读。
    """
    series = np.asarray(series, float)
    n = series.size
    obs = float(stat_fn(series))
    rng = np.random.default_rng(seed)
    diffs = np.diff(series)
    sd = float(np.std(diffs)) if diffs.size else float(np.std(series))
    sims = np.empty(n_sim)
    for b in range(n_sim):
        inc = rng.normal(0, sd if sd > 0 else 1.0, n)
        s = np.cumsum(inc) if null == "rw" else inc
        sims[b] = stat_fn(s)
    lo, hi = np.percentile(sims, [2.5, 97.5])
    p = float((np.sum(sims >= obs) + 1) / (n_sim + 1))
    return {"observed": obs, "null": null, "null_mean": float(sims.mean()),
            "null_band95": (float(lo), float(hi)),
            "p_one_sided": p, "exceeds_null": bool(obs > hi)}


# ───────────────────── §1 Layer2：方向技能检验 ─────────────────────


def pesaran_timmermann(pred_up: np.ndarray, true_up: np.ndarray) -> dict:
    """Pesaran–Timmermann 1992 方向准确性独立性检验（vs 仅靠基率撞对）。"""
    a = np.asarray(pred_up, int)
    b = np.asarray(true_up, int)
    n = a.size
    if n < 5:
        return {"hit": np.nan, "pt": np.nan, "p": np.nan, "n": n}
    hit = float(np.mean(a == b))
    py = b.mean()
    px = a.mean()
    pstar = py * px + (1 - py) * (1 - px)
    var_p = pstar * (1 - pstar) / n
    var_ps = (((2 * py - 1) ** 2) * px * (1 - px) / n
              + ((2 * px - 1) ** 2) * py * (1 - py) / n
              + 4 * py * px * (1 - py) * (1 - px) / n ** 2)
    denom = var_p - var_ps
    if denom <= 0:
        return {"hit": hit, "pt": np.nan, "p": np.nan, "n": n,
                "_note": "var 退化（pred/true 近常数）"}
    pt = (hit - pstar) / np.sqrt(denom)
    return {"hit": hit, "expected_by_chance": float(pstar),
            "pt": float(pt), "p": float(stats.norm.sf(pt)), "n": n}


def diebold_mariano(e1: np.ndarray, e2: np.ndarray, h: int = 1,
                     loss: str = "se") -> dict:
    """Diebold–Mariano 1995 + Harvey–Leybourne–Newbold 小样本校正。

    检验两预测损失是否有别（e* = 预测误差）。loss: 'se' 平方 / 'ae' 绝对。
    """
    e1 = np.asarray(e1, float)
    e2 = np.asarray(e2, float)
    L = (lambda e: e ** 2) if loss == "se" else (lambda e: np.abs(e))
    d = L(e1) - L(e2)
    n = d.size
    if n < 5:
        return {"dm": np.nan, "p": np.nan, "n": n}
    dbar = d.mean()
    g0 = np.var(d, ddof=0)
    gamma = g0
    for k in range(1, h):
        gamma += 2.0 * np.dot(d[k:] - dbar, d[:-k] - dbar) / n
    var = max(gamma / n, 1e-18)
    dm = dbar / np.sqrt(var)
    hln = np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)  # HLN 校正
    dm_adj = dm * hln
    p = 2.0 * stats.t.sf(abs(dm_adj), df=n - 1)
    return {"dm": float(dm), "dm_hln": float(dm_adj), "p": float(p), "n": n,
            "favors": "f2" if dbar > 0 else "f1"}


def clark_west(y, f_small, f_big) -> dict:
    """Clark–West 2007 嵌套模型 OOS 检验（大模型是否真有样本外增益）。"""
    y = np.asarray(y, float)
    f1 = np.asarray(f_small, float)
    f2 = np.asarray(f_big, float)
    adj = (y - f1) ** 2 - ((y - f2) ** 2 - (f1 - f2) ** 2)
    r = hac_mean_tstat(adj)
    return {"cw_mean": r["mean"], "cw_t": r["t"], "p_one_sided":
            float(stats.norm.sf(r["t"])) if np.isfinite(r["t"]) else np.nan,
            "n": r["n"], "big_model_adds": bool(np.isfinite(r["t"])
                                                and r["t"] > 0)}


# ───────────────────── R6：BIS 单边 HP 信贷-GDP 缺口 ─────────────────────


def _hp_trend(y: np.ndarray, lam: float) -> np.ndarray:
    """两侧 HP 趋势闭式解：(I + λ KᵀK)⁻¹ y，K 为二阶差分算子。"""
    n = y.size
    if n < 3:
        return y.copy()
    I = np.eye(n)
    D = np.zeros((n - 2, n))
    for i in range(n - 2):
        D[i, i], D[i, i + 1], D[i, i + 2] = 1.0, -2.0, 1.0
    return np.linalg.solve(I + lam * D.T @ D, y)


def one_sided_hp_credit_gap(series: np.ndarray, lam: float = 400000.0) -> dict:
    """BIS 信贷-GDP 缺口：单边（real-time/point-in-time）HP，λ=400000（Basel III CCyB）。

    红队 R6：弃自创波动悖论指标，复用既有 EWI 法。单边=每点只用 ≤t 数据
    递归求 HP，取末端拟合值——无前视。返回 gap 与点位 trend。
    """
    series = np.asarray(series, float)
    n = series.size
    trend = np.full(n, np.nan)
    for t in range(n):
        if t < 2:
            trend[t] = series[t]
        else:
            trend[t] = _hp_trend(series[: t + 1], lam)[-1]
    gap = series - trend
    return {"gap": gap, "trend": trend, "lam": lam,
            "_note": "单边递归 HP，每点仅用 ≤t 数据，无前视；λ=400000 Basel III"}
