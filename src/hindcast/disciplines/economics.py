"""经济学派 (4 lens). prompt 文本从 hindcast.schools 引用, 不复制不修改.

4 派定位见 17-ADR 学派账本; 21-ADR 叙事模拟器升级后, 经济派仍保留账本机制
(历史 tab 进 majority_vote + GT 对账; 现实事件 tab 不出方向, 跟其它学科一致只讲 frame).
"""
from __future__ import annotations

from hindcast.disciplines import LAYER_MATERIAL, Lens, register
from hindcast.schools import (
    AUSTRIAN_PROMPT,
    KEYNESIAN_PROMPT,
    MONETARIST_PROMPT,
    RATIONAL_EXP_PROMPT,
)

AUSTRIAN = register(Lens(
    id="austrian",
    discipline="economics",
    label_en="Austrian",
    label_zh="奥地利学派",
    prompt=AUSTRIAN_PROMPT,
    layer=LAYER_MATERIAL,
    color="#d97706",
    is_voting=True,
    is_account_ledger=True,
    metadata={"thinkers": ["Mises", "Hayek", "Rothbard"]},
))

MONETARIST = register(Lens(
    id="monetarist",
    discipline="economics",
    label_en="Monetarist",
    label_zh="货币主义",
    prompt=MONETARIST_PROMPT,
    layer=LAYER_MATERIAL,
    color="#2563eb",
    is_voting=True,
    is_account_ledger=True,
    metadata={"thinkers": ["Friedman", "Schwartz", "Lucas"]},
))

KEYNESIAN = register(Lens(
    id="keynesian",
    discipline="economics",
    label_en="Keynesian",
    label_zh="凯恩斯主义",
    prompt=KEYNESIAN_PROMPT,
    layer=LAYER_MATERIAL,
    color="#059669",
    is_voting=True,
    is_account_ledger=True,
    metadata={"thinkers": ["Keynes", "Minsky", "Krugman", "Kelton (MMT)"]},
))

RATIONAL_EXPECTATIONS = register(Lens(
    id="rational_expectations",
    discipline="economics",
    label_en="Rational Expectations",
    label_zh="理性预期",
    prompt=RATIONAL_EXP_PROMPT,
    layer=LAYER_MATERIAL,
    color="#7c3aed",
    is_voting=True,
    is_account_ledger=True,
    metadata={"thinkers": ["Fama", "Lucas", "Sargent", "Shiller (counter)"]},
))
