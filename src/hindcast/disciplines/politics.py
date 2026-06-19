"""政治学 (1 lens: 制度政治经济学派). prompt 文本从 hindcast.schools 引用.

v0.5.6 接入, +7pp 战绩 (见 then_vs_now.json). 21-ADR pivot 后定位为
叙事供给学科, 不投票不进账本; 在动态 chain 里是 institution 层.
"""
from __future__ import annotations

from hindcast.disciplines import LAYER_INSTITUTION, Lens, register
from hindcast.schools import INSTITUTIONAL_PE_PROMPT

INSTITUTIONAL_PE = register(Lens(
    id="institutional_pe",
    discipline="politics",
    label_en="Institutional Political Economy",
    label_zh="制度政治经济学派",
    prompt=INSTITUTIONAL_PE_PROMPT,
    layer=LAYER_INSTITUTION,
    color="#b45309",  # amber-700, 跟前端政治简报折叠卡琥珀调一致
    is_voting=False,        # 不投票 — 21-ADR 学科分层
    is_account_ledger=False,  # 不进账本 — 21-ADR 学科分层
    metadata={
        "thinkers": ["North", "Olson", "Ostrom", "Acemoglu-Robinson"],
        "rag_corpus": "institutional_pe",  # RAG 子图名 (RAG_TO_HINDCAST_REPLY_2026-05-21)
    },
))
