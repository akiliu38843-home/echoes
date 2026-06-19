"""18-ADR 诚实边界自动回归守卫 —— 把"不变量"从文档升级成可执行检查。

源码层结构断言：**不 import 业务、不调 LLM、不联网、确定性、毫秒级**。
任何后续编辑一旦悄悄破坏 18-ADR 边界（出现 advice / 丢 honest_frame /
削弱咨询章程 / 破咨询数据防火墙），本测试即红灯。

跑：PYTHONPATH=src .venv/bin/python -m pytest tests/test_honest_boundary.py -q
或独立：PYTHONPATH=src .venv/bin/python tests/test_honest_boundary.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "hindcast"
WEB = (SRC / "web.py").read_text(encoding="utf-8")
CONSULT = (SRC / "consult.py").read_text(encoding="utf-8")

# 预测族端点：其函数体必须经诚实框（_with_honest / _forecast_payload）或内联齐全
_PREDICT_ROUTES = re.findall(
    r'@app\.post\("(/api/(?:predict[^"]*|consult))"\)\s*\n'
    r'(?:async )?def (\w+)\(', WEB)


def _fn_body(name: str) -> str:
    m = re.search(rf"\ndef {re.escape(name)}\(.*?(?=\n@app\.|\nclass |\ndef "
                  r"[a-zA-Z_]|\Z)", WEB, re.S)
    return m.group(0) if m else ""


def test_no_advice_anywhere() -> None:
    """is_advice 恒 False —— 全 web.py 不得出现 is_advice True。"""
    assert re.search(r'is_advice"?\s*[:=]\s*True', WEB) is None, \
        "web.py 出现 is_advice=True —— 违反 18-ADR（产品不给配置/方向建议）"


def test_with_honest_attaches_all() -> None:
    """_with_honest 必须同时挂 honest_frame + i18n + stance + is_advice False。"""
    m = re.search(r"def _with_honest\(.*?\n    return payload", WEB, re.S)
    assert m, "_with_honest 不见了"
    b = m.group(0)
    for need in ('"honest_frame"', '"honest_frame_i18n"', '"stance"',
                 '"is_advice"', "False"):
        assert need in b, f"_with_honest 缺 {need}"


def test_forecast_payload_has_honest() -> None:
    m = re.search(r"def _forecast_payload\(.*?\n    return payload", WEB, re.S)
    assert m, "_forecast_payload 不见了"
    b = m.group(0)
    for need in ('"honest_frame"', '"honest_frame_i18n"', '"stance"',
                 '"is_advice": False'):
        assert need in b, f"_forecast_payload 缺 {need}"


def test_every_predict_endpoint_goes_through_honest() -> None:
    """每个 predict/consult 端点都必须经诚实框，无旁路。"""
    assert _PREDICT_ROUTES, "没扫到 predict 端点（正则失配？）"
    for path, fn in _PREDICT_ROUTES:
        body = _fn_body(fn)
        assert body, f"{fn} 函数体未定位"
        ok = ("_with_honest(" in body or "_forecast_payload(" in body
              or ("honest_frame" in body and "is_advice" in body))
        assert ok, f"端点 {path}({fn}) 未经诚实框 —— 18-ADR 旁路！"


def test_honest_frame_bilingual_defined() -> None:
    for tok in ("HONEST_FRAME = {", "HONEST_FRAME_EN = {",
                "HONEST_FRAME_I18N = {"):
        assert tok in WEB, f"web.py 缺 {tok}"
    en = re.search(r"HONEST_FRAME_EN = \{.*?\n\}", WEB, re.S).group(0)
    assert "not investment" in en and "negative value" in en, \
        "HONEST_FRAME_EN 英文未明确'非投资建议/负价值'"


def test_consult_charter_hard_rules() -> None:
    """咨询章程硬红线不得被削弱。"""
    assert "CONSULT_CHARTER" in CONSULT
    for rule in ("不给任何具体买卖", "假精度", "你自己的决定", "不是投资建议"):
        assert rule in CONSULT, f"咨询章程缺硬红线片段：{rule}"


def test_consult_data_firewall() -> None:
    """咨询模块绝不 import 账本/连续回测/学派 verdict 通道（17/18-ADR 防火墙）。"""
    for banned in (r"\bimport\s+\w*school_ledger", r"\bfrom\s+\S*school_ledger",
                   r"\bimport\s+\w*continuous", r"\bfrom\s+\S*continuous",
                   r"\bfrom\s+hindcast\.agents\b", r"\bimport\s+\w*\bagents\b"):
        assert re.search(banned, CONSULT) is None, \
            f"consult.py 触碰禁止依赖（数据防火墙破）：/{banned}/"


def test_consult_prompt_is_persona_plus_charter_not_predictor() -> None:
    """系统提示 = 人格 + 章程，且剥离预测 OUTPUT_FORMAT（不是预测器）。"""
    m = re.search(r"def build_system_prompt\(.*?\n\n", CONSULT, re.S)
    assert m and "_persona(" in m.group(0) and "CONSULT_CHARTER" in m.group(0)
    assert "OUTPUT_FORMAT" not in CONSULT, "咨询不应携带预测 OUTPUT_FORMAT"


def main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = []
    for fn in fns:
        try:
            fn()
            print(f"[PASS] {fn.__name__}")
        except AssertionError as e:
            fails.append(fn.__name__)
            print(f"[FAIL] {fn.__name__} · {e}")
    print("\n" + "=" * 60)
    if fails:
        print(f"❌ {len(fails)} FAIL: {fails}")
        return 1
    print(f"✅ 全部 PASS（{len(fns)} 项）—— 18-ADR 诚实边界已焊成可执行守卫，"
          "后续任何编辑破线即红灯")
    return 0


if __name__ == "__main__":
    sys.exit(main())
