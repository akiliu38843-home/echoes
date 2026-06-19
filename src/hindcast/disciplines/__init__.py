"""学科 + 立场 (lens) 注册表.

替代 state.py 里的 SCHOOLS 硬编码常量 + schools.py 的 PROMPTS dict.
设计目标: 加新学科 = 新建一个 disciplines/<name>.py + @register, 不动其他文件.

# 架构 (21-ADR 叙事模拟器 + 22-ADR 动态学科 chain)
- 学科 (discipline): "economics" / "politics" / "history" / "sociology" / ...
- 立场 (lens):       学科内部的视角. 一个学科可有多个 lens.
                     例: economics 4 派 (奥/货/凯/理); history 2 立场 (长时段 / 偶然性).
- 维度层 (layer):    "spacetime" / "institution" / "material" / "psyche_culture"
                     决定串行 chain 的位置. 22-ADR 维度优先级.
- 投票/账本元数据:    is_voting (是否进 majority_vote) / is_account_ledger (是否对 GT 算 hit)
                     经济派 True, 其它学科 False (叙事供给, 不算分).

# 并存策略 (refactor 安全)
当前 (Tier 1 refactor): 旧 SCHOOLS 常量 + PROMPTS dict 仍在 state.py / schools.py 里,
本 registry 并行存在; 后续 Tier 2 把消费方逐步切到 registry, 验证后再删旧路径.
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "Lens",
    "register",
    "discipline_lenses",
    "all_disciplines",
    "get_lens",
    "list_lens_ids",
]


# ─── 维度层常量 (22-ADR 固定顺序) ───
LAYER_SPACETIME = "spacetime"        # 历史 / 地理
LAYER_INSTITUTION = "institution"    # 政治 / 法学
LAYER_MATERIAL = "material"          # 经济
LAYER_PSYCHE_CULTURE = "psyche_culture"  # 社会 / 人类 / 心理 / 宗教 / STS / ...

LAYER_ORDER = [
    LAYER_SPACETIME,
    LAYER_INSTITUTION,
    LAYER_MATERIAL,
    LAYER_PSYCHE_CULTURE,
]


@dataclass(frozen=True)
class Lens:
    """单个 lens (立场). 一个学科下可有多个 lens.

    frozen=True: 防止运行期被改, 注册后不可变. 修改 prompt 须重启或重新 register.
    """

    id: str                          # e.g. "austrian", "long_durée"
    discipline: str                  # e.g. "economics", "history"
    label_en: str
    label_zh: str
    prompt: str                      # system prompt 文本 (含 OUTPUT_FORMAT 等共享尾巴)
    layer: str                       # 维度层 (见 LAYER_*)
    color: str | None = None         # 前端展示色 (hex)
    is_voting: bool = False          # 是否进 majority_vote (仅经济派 True)
    is_account_ledger: bool = False  # 是否对 GT 算 hit (仅经济派 True)
    is_required: bool = False        # router 是否必调 (历史/中枢大脑 True; 其它 router 决定)
    metadata: dict = field(default_factory=dict)


# 全局 registry: discipline_name → list of Lens
_REGISTRY: dict[str, list[Lens]] = {}


def register(lens: Lens) -> Lens:
    """注册一个 lens. 返回 lens 本身, 方便子模块在顶层 `X = register(Lens(...))`."""
    if lens.discipline not in _REGISTRY:
        _REGISTRY[lens.discipline] = []
    # 防重复注册同 id (热重载 / 多次 import 保护)
    existing_ids = [l.id for l in _REGISTRY[lens.discipline]]
    if lens.id in existing_ids:
        return lens  # 已注册, 不重复
    _REGISTRY[lens.discipline].append(lens)
    return lens


def discipline_lenses(discipline: str) -> list[Lens]:
    """取某学科的所有 lens. 顺序按注册顺序."""
    return list(_REGISTRY.get(discipline, []))


def all_disciplines() -> list[str]:
    """所有已注册学科."""
    return list(_REGISTRY.keys())


def get_lens(lens_id: str, discipline: str | None = None) -> Lens | None:
    """按 lens_id 找 lens. discipline 可选用于 disambiguation (不同学科可重名)."""
    for d, lenses in _REGISTRY.items():
        if discipline and d != discipline:
            continue
        for lens in lenses:
            if lens.id == lens_id:
                return lens
    return None


def list_lens_ids(discipline: str) -> tuple[str, ...]:
    """取某学科所有 lens id (常用于 backward compat: SCHOOLS = list_lens_ids("economics"))."""
    return tuple(l.id for l in _REGISTRY.get(discipline, []))


# ─── 子模块注册 ───
# 子模块 import 时执行 register(Lens(...)). 注意循环依赖: 子模块 import 本模块的
# Lens + register 时, 上面所有 symbols 已定义, Python 能从 partially-loaded
# hindcast.disciplines 拿到它们.
from hindcast.disciplines import economics       # noqa: E402, F401
from hindcast.disciplines import politics        # noqa: E402, F401
from hindcast.disciplines import history         # noqa: E402, F401
from hindcast.disciplines import sociology       # noqa: E402, F401
from hindcast.disciplines import anthropology    # noqa: E402, F401
from hindcast.disciplines import intl_relations  # noqa: E402, F401
from hindcast.disciplines import central_brain   # noqa: E402, F401
