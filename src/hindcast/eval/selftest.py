"""hindcast.eval 自验：每个量具在合成数据上行为正确。

零外部数据、零被冻通道、零可计数产品结论——只验"尺子本身刻度对不对"。
跑：  PYTHONPATH=src .venv/bin/python -m hindcast.eval.selftest
任一 FAIL → 退出码 1。
"""
from __future__ import annotations

import sys

import numpy as np

from hindcast.eval import metrics as M

_fails: list[str] = []


def chk(name: str, cond: bool, detail: str = "") -> None:
    tag = "PASS" if cond else "FAIL"
    if not cond:
        _fails.append(name)
    print(f"[{tag}] {name}{('  · ' + detail) if detail else ''}")


def main() -> int:
    rng = np.random.default_rng(42)

    # 1) HAC：正自相关下 HAC se 应 > 朴素 se（朴素 t 被夸大）
    n = 400
    ar = np.zeros(n)
    for t in range(1, n):
        ar[t] = 0.7 * ar[t - 1] + rng.normal()
    ar += 0.15
    hac = M.hac_mean_tstat(ar)
    naive_se = np.std(ar, ddof=1) / np.sqrt(n)
    chk("hac_mean_tstat 放大自相关 se", hac["se"] > naive_se * 1.3,
        f"HAC se={hac['se']:.4f} > 朴素 {naive_se:.4f}, lags={hac['lags']}")

    # 2) 移动块自助：AR(1) 上块 CI 应比 iid 百分位 CI 宽
    mbb = M.moving_block_bootstrap_ci(ar, np.mean, n_boot=1500, seed=1)
    iidboot = np.array([rng.choice(ar, n, replace=True).mean()
                        for _ in range(1500)])
    iid_w = np.subtract(*np.percentile(iidboot, [97.5, 2.5]))
    mbb_w = mbb["hi"] - mbb["lo"]
    chk("moving_block_bootstrap_ci 保留依赖(更宽)", mbb_w > iid_w,
        f"块宽={mbb_w:.4f} > iid宽={iid_w:.4f}, blk={mbb['block']}")

    # 3) AUC-PR：有技能 ≫ 基率；随机 ≈ 基率
    nN = 4000
    y = (rng.random(nN) < 0.08).astype(int)          # ~8% 稀有
    skill = np.clip(0.08 + 0.6 * y + rng.normal(0, 0.15, nN), 0, 1)
    randp = rng.random(nN)
    base = y.mean()
    chk("pr_auc 有技能 ≫ 基率", M.pr_auc(skill, y) > 0.4,
        f"AP_skill={M.pr_auc(skill,y):.3f} vs base={base:.3f}")
    chk("pr_auc 随机 ≈ 基率", abs(M.pr_auc(randp, y) - base) < 0.05,
        f"AP_rand={M.pr_auc(randp,y):.3f} ≈ {base:.3f}")
    chk("log_loss 有技能 < 随机",
        M.log_loss(skill, y) < M.log_loss(randp, y))
    chk("brier_skill_score 标注为次要",
        "次要" in M.brier_skill_score(skill, y)["_warning"])

    # 4) 可靠性带：完美校准多数 in_band；恒 0 预测应多数出带
    p_true = rng.random(3000) * 0.9 + 0.05
    y_cal = (rng.random(3000) < p_true).astype(int)
    rb = M.reliability_bins(p_true, y_cal, 10)
    in_rate = np.mean([b["in_band"] for b in rb])
    rb_bad = M.reliability_bins(p_true, np.zeros(3000, int), 10)
    bad_in = np.mean([b["in_band"] for b in rb_bad])
    chk("reliability 完美校准多在带内", in_rate >= 0.7,
        f"in_band={in_rate:.2f}")
    chk("reliability 错校准多出带", bad_in <= 0.4, f"in_band={bad_in:.2f}")

    # 5) 振幅 vs null：纯随机游走不应"超 null"；注入大摆动应超
    rw = np.cumsum(rng.normal(0, 1, 300))
    a_rw = M.amplitude_vs_null(rw, null="rw", n_sim=1500, seed=2)
    chk("amplitude 随机游走不超 null", not a_rw["exceeds_null"],
        f"obs={a_rw['observed']:.1f} band≤{a_rw['null_band95'][1]:.1f}")
    rw2 = rw.copy()
    rw2[150:] += np.linspace(0, 60, 150)        # 注入确定性大摆
    a_big = M.amplitude_vs_null(rw2, null="rw", n_sim=1500, seed=2)
    chk("amplitude 注入大摆超 null", a_big["exceeds_null"],
        f"obs={a_big['observed']:.1f} p={a_big['p_one_sided']:.3f}")

    # 6) Pesaran–Timmermann：独立 → 不显著；对齐 → 显著
    tu = (rng.random(500) < 0.5).astype(int)
    indep = (rng.random(500) < 0.5).astype(int)
    aligned = np.where(rng.random(500) < 0.8, tu, 1 - tu)
    chk("PT 独立不显著", M.pesaran_timmermann(indep, tu)["p"] > 0.05)
    chk("PT 对齐显著", M.pesaran_timmermann(aligned, tu)["p"] < 0.01,
        f"hit={M.pesaran_timmermann(aligned,tu)['hit']:.2f}")

    # 7) Diebold–Mariano：f2 真更优 → 显著且 favors f2
    truth = rng.normal(0, 1, 300)
    e_bad = truth + rng.normal(0, 1.0, 300)
    e_good = truth + rng.normal(0, 0.3, 300)
    dm = M.diebold_mariano(truth - (truth - e_bad), truth - (truth - e_good))
    # 传入预测误差：e1 大、e2 小 → favors f2
    dm = M.diebold_mariano(e_bad, e_good)
    chk("DM 识别更优预测", dm["p"] < 0.05 and dm["favors"] == "f2",
        f"p={dm['p']:.4f} favors={dm['favors']}")

    # 8) Clark–West：大模型真有增益 → big_model_adds & p 小
    yv = rng.normal(0, 1, 300)
    f_small = np.zeros(300)
    f_big = 0.6 * yv + rng.normal(0, 0.4, 300)   # 真带 y 信息
    cw = M.clark_west(yv, f_small, f_big)
    chk("CW 识别大模型增益", cw["big_model_adds"] and cw["p_one_sided"] < 0.05,
        f"t={cw['cw_t']:.2f} p={cw['p_one_sided']:.4f}")

    # 9) 单边 HP：缺口能复出周期；★点位不变性=无前视（本线主题硬验）★
    tt = np.arange(240, dtype=float)
    base_series = 0.05 * tt + 4.0 * np.sin(2 * np.pi * tt / 40)
    r1 = M.one_sided_hp_credit_gap(base_series, lam=400000)
    chk("单边HP 缺口非全零(复出周期)",
        np.nanstd(r1["gap"][10:]) > 0.5,
        f"std(gap)={np.nanstd(r1['gap'][10:]):.2f}")
    s2 = base_series.copy()
    s2[200:] += 999.0                            # 篡改未来段
    r2 = M.one_sided_hp_credit_gap(s2, lam=400000)
    same = np.allclose(r1["trend"][:150], r2["trend"][:150], atol=1e-9)
    chk("★单边HP 无前视：改未来不动过去 trend★", same,
        "trend[:150] 篡改未来后仍逐位相等" if same else "前视泄漏!")

    print("\n" + "=" * 60)
    if _fails:
        print(f"❌ {len(_fails)} FAIL: {_fails}")
        return 1
    print("✅ 全部 PASS —— 评估量具刻度正确，可待 #2 干净数据接入")
    return 0


if __name__ == "__main__":
    sys.exit(main())
