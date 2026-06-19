"""预注册评估流水线 —— 把已锁死的协议编成不可篡改、自动判定的代码。

协议来源（**全部已冻结、跑前定死跑后不改**）：
  `HINDCAST_TO_RAG_REPLY_2026-05-18_POINTINTIME_TEST1_AUTHORIZE.md`（5% 死线/分母/翻定义/双层/负面对称）
  `HINDCAST_TO_RAG_REPLY_2026-05-19_POINTINTIME_TEST1_SCOPE_ADDENDUM.md`（规矩A 限定范围/规矩B 功效底线15/B1/B2）
  `19-ADR-DATA-VINTAGE-INTEGRITY.md`（单向墙+三不变量）

设计铁律：
  • `Criterion` 是 **frozen dataclass**——判据是常数，构造后无法被任何调用方篡改
    （任何"见结果再挪门槛"在代码层就抛 FrozenInstanceError）。
  • 纯函数、确定性：同输入恒同裁定；**自身不取任何数据、不产可计数产品结论**——
    只有当 #2 把"真 vintage vs revised 逐点重算结果"喂进来时才出裁定。
  • 与 RAG #2 文件零交叉；只依赖 stdlib + 本包；放 `hindcast/eval/`。

#2 通后用法：把每个催化点在 revised 与真 vintage 下的 (fired,tier,regime) 喂成
`Point` 列表 → `judge(...)` → 自动出 GO_SCOPED / NO_GO / SUSPEND_POWER + 审计表。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    GO_SCOPED = "GO_SCOPED"            # 翻盘 ≤ 死线 且 功效达标 —— 限定范围计数
    NO_GO = "NO_GO"                   # 翻盘 > 死线 —— 作废
    SUSPEND_POWER = "SUSPEND_POWER"   # 判得了的 CPI 承重点 < 功效底线 —— 功效不足→悬置(不撤不解挂)


@dataclass(frozen=True)
class Criterion:
    """已锁死判据。frozen=True：构造后不可改（防"见结果挪门槛"=红队R1/17-ADR§4自欺）。"""
    flip_line: float = 0.05      # AUTHORIZE 5% 死线
    power_floor: int = 15        # SCOPE_ADDENDUM 规矩B：复用红队§2/17-ADR§5c.5 R3 旧尺 15
    ci_alpha: float = 0.05       # B1：二项 Wilson 95% CI
    provenance: str = (
        "FROZEN: TEST1_AUTHORIZE(5%/分母=CPI承重/翻=进出∨档∨性质/双层/负面对称) "
        "+ SCOPE_ADDENDUM(规矩A限定范围/规矩B功效15/B1不许说已证清白/B2按层各套) "
        "+ 19-ADR(单向墙+三不变量)。跑前冻结，跑后不改。"
    )


@dataclass(frozen=True)
class Point:
    """一个催化点在两种数据源下的状态。judged=False 即'无法判定'(ALFRED 无 vintage)。"""
    date: str
    cpi_bearing: bool                 # 是否'靠 CPI 信号才进来/才定档'(分母资格)
    judged: bool                      # 真 vintage 可得？False→无法判定，单列续挂、绝不并入干净
    layers: tuple = ("333",)          # 该点属于哪些层：'333' 主判 / '50' 副报
    rev_fired: bool = False
    rev_tier: str | None = None
    rev_regime: str | None = None     # 'inflation' | 'deflation' | None
    vin_fired: bool = False
    vin_tier: str | None = None
    vin_regime: str | None = None


def wilson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """二项比例 Wilson 分数区间（B1 要求附 CI；小 N 比 normal-approx 稳）。"""
    if n == 0:
        return (float("nan"), float("nan"))
    z = _z(1 - alpha / 2)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def _z(q: float) -> float:
    """标准正态分位（Acklam 逼近，避免引 scipy 仅为一个分位）。"""
    a = [-3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2,
         1.383577518672690e2, -3.066479806614716e1, 2.506628277459239e0]
    b = [-5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2,
         6.680131188771972e1, -1.328068155288572e1]
    c = [-7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838e0,
         -2.549732539343734e0, 4.374664141464968e0, 2.938163982698783e0]
    d = [7.784695709041462e-3, 3.224671290700398e-1, 2.445134137142996e0,
         3.754408661907416e0]
    pl, ph = 0.02425, 1 - 0.02425
    if q < pl:
        u = math.sqrt(-2 * math.log(q))
        return (((((c[0]*u+c[1])*u+c[2])*u+c[3])*u+c[4])*u+c[5]) / \
               ((((d[0]*u+d[1])*u+d[2])*u+d[3])*u+1)
    if q <= ph:
        u = q - 0.5
        r = u * u
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*u / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    u = math.sqrt(-2 * math.log(1 - q))
    return -(((((c[0]*u+c[1])*u+c[2])*u+c[3])*u+c[4])*u+c[5]) / \
            ((((d[0]*u+d[1])*u+d[2])*u+d[3])*u+1)


def is_flip(p: Point) -> bool:
    """翻 = judged 且 cpi_bearing 且 (进出 ∨ 档 ∨ 性质 任一变)。无法判定不算翻、也不算干净。"""
    if not (p.judged and p.cpi_bearing):
        return False
    if p.rev_fired != p.vin_fired:
        return True
    if p.rev_fired and p.vin_fired:                       # 仍在内才比档/性质
        if (p.rev_tier or "") != (p.vin_tier or ""):
            return True
        if (p.rev_regime or "") != (p.vin_regime or ""):
            return True
    return False


@dataclass
class LayerResult:
    layer: str
    denom_n: int               # CPI 承重点总数(该层)
    judged_n: int              # 判得了
    unjudged_n: int            # 无法判定(单列续挂，绝不并入干净)
    unjudged_dates: list = field(default_factory=list)
    flips: int = 0
    flip_rate: float = float("nan")
    ci95: tuple = (float("nan"), float("nan"))
    verdict: Verdict = Verdict.SUSPEND_POWER
    statement: str = ""


def judge_layer(points: list[Point], layer: str, crit: Criterion) -> LayerResult:
    """单层裁定。规矩A：先报判得了/判不了拆分；判不了单列、绝不并入干净。
    规矩B：判得了 CPI 承重 < power_floor → SUSPEND_POWER(翻盘率再好也不 GO)。
    B1：过线只报'过最低门槛+N弱+CI'，绝不'已证清白'。"""
    denom = [p for p in points if layer in p.layers and p.cpi_bearing]
    judged = [p for p in denom if p.judged]
    unjudged = [p for p in denom if not p.judged]
    r = LayerResult(layer=layer, denom_n=len(denom), judged_n=len(judged),
                    unjudged_n=len(unjudged),
                    unjudged_dates=sorted(p.date for p in unjudged))

    if len(judged) < crit.power_floor:
        r.verdict = Verdict.SUSPEND_POWER
        r.statement = (
            f"[{layer}层] 判得了 CPI 承重 {len(judged)} < 功效底线 {crit.power_floor} "
            f"→ 功效不足→悬置（即便翻盘率好看也不 GO，不撤不解挂）。"
            f"判不了 {len(unjudged)} 单列续挂，绝不并入干净。")
        return r

    flips = [p for p in judged if is_flip(p)]
    r.flips = len(flips)
    r.flip_rate = len(flips) / len(judged)
    r.ci95 = wilson_ci(len(flips), len(judged), crit.ci_alpha)

    if r.flip_rate > crit.flip_line:
        r.verdict = Verdict.NO_GO
        r.statement = (
            f"[{layer}层] 翻盘 {r.flips}/{len(judged)} = {r.flip_rate:.1%} "
            f"Wilson95%CI[{r.ci95[0]:.1%},{r.ci95[1]:.1%}] > 死线 {crit.flip_line:.0%} "
            f"→ NO-GO，该层产物作废。")
        return r

    r.verdict = Verdict.GO_SCOPED
    r.statement = (
        f"[{layer}层] **GO（限定范围，非'已证清白'）**：仅覆盖判得了的 {len(judged)} "
        f"个可查点；{len(unjudged)} 个无法判定**维持挂起、单列**（不并入、不以 revised 兜底）。"
        f"过项目预注册最低门槛(N={len(judged)}≥{crit.power_floor})，**N 受限、确定性弱**；"
        f"翻盘 {r.flips}/{len(judged)} = {r.flip_rate:.1%} "
        f"Wilson95%CI[{r.ci95[0]:.1%},{r.ci95[1]:.1%}] ≤ 死线 {crit.flip_line:.0%}。")
    return r


@dataclass
class Decision:
    criterion_provenance: str
    layer_333: LayerResult
    layer_50: LayerResult
    negative_verdict: Verdict
    negative_statement: str
    overall_go: bool             # 仅当 333 层 GO_SCOPED；50 层/负面 各自独立(B2)
    audit_table: list = field(default_factory=list)
    summary: str = ""


def judge(points: list[Point], crit: Criterion,
          negative_holds_on_clean=None) -> Decision:
    """总裁定。333 层 = GO/NO-GO 基准；50 层 = 副报、独立判(B2：333 GO 不自动解挂 50)。
    负面结果对称复核：只在'未翻的干净点'上重评，且干净点须 ≥ 功效底线。

    negative_holds_on_clean: 可选回调 (clean_points)->bool；缺省=无法重评→保持悬置。
    """
    v333 = judge_layer(points, "333", crit)
    v50 = judge_layer(points, "50", crit)

    # 负面结果：仅未翻的干净点(judged 且非 flip)；干净 N < 底线 → 不撤不解挂
    clean = [p for p in points if p.judged and p.cpi_bearing and not is_flip(p)]
    if len(clean) < crit.power_floor:
        neg_v = Verdict.SUSPEND_POWER
        neg_s = (f"负面对称复核：干净点 {len(clean)} < {crit.power_floor} "
                 f"→ 功效不足→悬置，**既不撤销也不解挂**（对称纪律：污染双向扭曲）。")
    elif negative_holds_on_clean is None:
        neg_v = Verdict.SUSPEND_POWER
        neg_s = (f"负面对称复核：干净点 {len(clean)}≥{crit.power_floor} 但未提供干净重评回调 "
                 f"→ 暂保持悬置，待真重评。")
    else:
        holds = bool(negative_holds_on_clean(clean))
        neg_v = Verdict.GO_SCOPED if holds else Verdict.NO_GO
        neg_s = (f"负面对称复核：干净点 {len(clean)}≥{crit.power_floor}，"
                 f"结论在干净子集上{'仍成立→可解除悬置(限定范围)' if holds else '不成立→撤销该负面结论'}。")

    overall = v333.verdict == Verdict.GO_SCOPED
    audit = [{
        "date": p.date, "layers": list(p.layers), "cpi_bearing": p.cpi_bearing,
        "judged": p.judged,
        "revised": (p.rev_fired, p.rev_tier, p.rev_regime),
        "vintage": (p.vin_fired, p.vin_tier, p.vin_regime),
        "flip": is_flip(p),
        "note": "" if p.judged else "无法判定·单列续挂·绝不并入干净",
    } for p in sorted(points, key=lambda x: x.date)]

    summary = (
        f"333主判={v333.verdict.value} | 50副报={v50.verdict.value}"
        f"（B2：50 层独立，333 GO 不自动解挂 50）| 负面={neg_v.value}。"
        f"overall_go(仅依 333)={overall}。"
        + (" 注：50/负面 即便 333 GO 仍须各自过功效+范围才解挂。"
           if overall else ""))
    return Decision(
        criterion_provenance=crit.provenance,
        layer_333=v333, layer_50=v50,
        negative_verdict=neg_v, negative_statement=neg_s,
        overall_go=overall, audit_table=audit, summary=summary)
