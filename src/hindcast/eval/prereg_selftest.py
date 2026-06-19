"""prereg.py 自验：用合成点集（含 #1 真实 76/112）证明它忠实编码了锁死协议。

零外部数据、零被冻通道、零可计数产品结论——只验"自动裁判的逻辑对不对、
判据能不能被篡改"。任一 FAIL → 退出码 1。
跑：PYTHONPATH=src .venv/bin/python -m hindcast.eval.prereg_selftest
"""
from __future__ import annotations

import dataclasses
import sys

from hindcast.eval.prereg import (
    Criterion,
    Point,
    Verdict,
    is_flip,
    judge,
    judge_layer,
)

_fails: list[str] = []


def chk(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'PASS' if cond else 'FAIL'}] {name}{('  · ' + detail) if detail else ''}")
    if not cond:
        _fails.append(name)


def mk(date, cpi=True, judged=True, layers=("333",),
       rev=(True, "中", "inflation"), vin=(True, "中", "inflation")) -> Point:
    return Point(date=date, cpi_bearing=cpi, judged=judged, layers=tuple(layers),
                 rev_fired=rev[0], rev_tier=rev[1], rev_regime=rev[2],
                 vin_fired=vin[0], vin_tier=vin[1], vin_regime=vin[2])


def main() -> int:
    C = Criterion()

    # ── is_flip 三种翻 + 不翻 + 无法判定 ──
    chk("is_flip 进出翻",
        is_flip(mk("d", rev=(True, "中", "inflation"), vin=(False, None, None))))
    chk("is_flip 档翻",
        is_flip(mk("d", rev=(True, "轻", "inflation"), vin=(True, "重", "inflation"))))
    chk("is_flip 性质翻",
        is_flip(mk("d", rev=(True, "中", "inflation"), vin=(True, "中", "deflation"))))
    chk("is_flip 不变=不翻", not is_flip(mk("d")))
    chk("is_flip 无法判定既不翻也不算干净",
        not is_flip(mk("d", judged=False, rev=(True, "中", "inflation"),
                       vin=(False, None, None))))
    chk("is_flip 非CPI承重不计",
        not is_flip(mk("d", cpi=False, rev=(True, "中", "inflation"),
                       vin=(False, None, None))))

    # ── 场景1：#1 真实 76/112 翻 → NO-GO ──
    pts1 = ([mk(f"f{i}", rev=(True, "中", "inflation"), vin=(False, None, None))
             for i in range(76)]
            + [mk(f"k{i}") for i in range(36)])
    r1 = judge_layer(pts1, "333", C)
    chk("#1 真实 76/112 → NO_GO",
        r1.verdict == Verdict.NO_GO and abs(r1.flip_rate - 76 / 112) < 1e-9,
        f"rate={r1.flip_rate:.1%} verdict={r1.verdict.value}")

    # ── 场景2：干净 1/30 ≤5% 且 N≥15 → GO_SCOPED，措辞守 B1 ──
    pts2 = ([mk(f"flip", rev=(True, "中", "inflation"), vin=(False, None, None))]
            + [mk(f"ok{i}") for i in range(29)])
    r2 = judge_layer(pts2, "333", C)
    chk("干净 1/30 → GO_SCOPED", r2.verdict == Verdict.GO_SCOPED,
        f"rate={r2.flip_rate:.1%}")
    chk("GO 措辞守 B1（限定范围/N弱/非已证清白）",
        "限定范围" in r2.statement and "确定性弱" in r2.statement
        and "已证清白" in r2.statement and "非'已证清白'" in r2.statement)

    # ── 场景3：判得了 10 < 15 且 0 翻 → SUSPEND_POWER（核心 B 铁律）──
    r3 = judge_layer([mk(f"p{i}") for i in range(10)], "333", C)
    chk("0 翻但 N=10<15 → SUSPEND_POWER（翻盘好看也不 GO）",
        r3.verdict == Verdict.SUSPEND_POWER, r3.statement[:40])

    # ── 场景4：规矩A 限定范围——无法判定单列、绝不并入分母/干净 ──
    pts4 = ([mk(f"j{i}") for i in range(20)]
            + [mk(f"u{i}", judged=False, rev=(True, "中", "inflation"),
                 vin=(False, None, None)) for i in range(8)])
    r4 = judge_layer(pts4, "333", C)
    chk("规矩A：denom28/judged20/unjudged8 且翻只算 judged",
        r4.denom_n == 28 and r4.judged_n == 20 and r4.unjudged_n == 8
        and r4.flips == 0 and r4.verdict == Verdict.GO_SCOPED,
        f"denom={r4.denom_n} judged={r4.judged_n} unjudged={r4.unjudged_n}")
    chk("规矩A：无法判定单列(dates)且措辞声明覆盖",
        len(r4.unjudged_dates) == 8 and "8 个无法判定" in r4.statement)

    # ── 场景5：B2 —— 333 GO 但 50 层独立 <15 → 50 悬置、不随 333 解挂 ──
    pts5 = ([mk(f"a{i}", layers=("333",)) for i in range(20)]          # 333 干净N20
            + [mk(f"b{i}", layers=("50",)) for i in range(10)])        # 50 仅10<15
    d5 = judge(pts5, C)
    chk("B2：333 GO_SCOPED 而 50 SUSPEND_POWER 独立",
        d5.layer_333.verdict == Verdict.GO_SCOPED
        and d5.layer_50.verdict == Verdict.SUSPEND_POWER
        and d5.overall_go is True
        and "不自动解挂 50" in d5.summary, d5.summary[:60])

    # ── 场景6：负面对称复核 ──
    # 干净点 <15 → 不撤不解挂
    d6a = judge([mk(f"c{i}") for i in range(8)], C)
    chk("负面：干净8<15 → SUSPEND_POWER 不撤不解挂",
        d6a.negative_verdict == Verdict.SUSPEND_POWER
        and "既不撤销也不解挂" in d6a.negative_statement)
    # 干净≥15 且回调 True → 解除(限定)；False → 撤销负面
    base20 = [mk(f"e{i}") for i in range(20)]
    chk("负面：干净≥15 + 干净仍成立 → GO_SCOPED",
        judge(base20, C, lambda cl: True).negative_verdict == Verdict.GO_SCOPED)
    chk("负面：干净≥15 + 干净不成立 → NO_GO(撤销负面)",
        judge(base20, C, lambda cl: False).negative_verdict == Verdict.NO_GO)

    # ── 场景7：确定性 ──
    chk("确定性：同输入恒同裁定",
        judge(pts5, C).summary == judge(pts5, C).summary
        and judge(pts5, C).layer_333.flip_rate
            == judge(pts5, C).layer_333.flip_rate)

    # ── 场景8：★判据不可篡改——改门槛直接抛错（反自欺铁律的代码兑现）★ ──
    raised = False
    try:
        C.flip_line = 0.99  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        raised = True
    chk("★Criterion frozen：见结果挪门槛在代码层即抛 FrozenInstanceError★",
        raised, "judge 不可能被'跑后改 5%'")

    print("\n" + "=" * 64)
    if _fails:
        print(f"❌ {len(_fails)} FAIL: {_fails}")
        return 1
    print("✅ 全部 PASS —— 预注册流水线忠实编码锁死协议，且判据不可篡改；"
          "等 #2 真 vintage 喂入即自动出 GO/NO-GO，无需临时搭、无法挪门槛")
    return 0


if __name__ == "__main__":
    sys.exit(main())
