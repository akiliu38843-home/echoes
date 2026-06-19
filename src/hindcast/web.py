"""FastAPI Web 后端——把 hindcast.predict() 包成 REST API，并服务单页前端。

API 端点：
  GET  /                            → 单页 index.html
  GET  /api/snapshots               → 列出 8 个历史时点
  GET  /api/state/{date}            → 拿某日的 15 变量结构状态
  POST /api/predict/{date}          → 跑 4 学派常态预测，返回 Forecast
  GET  /api/weekly-events           → 本周热点策展列表 (23-ADR)
  POST /api/narrative               → 叙事模拟 chain (22-ADR)

启动：
  hindcast web                      # 默认 0.0.0.0:8000
  hindcast web --port 8080
"""

from __future__ import annotations

from pathlib import Path

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from hindcast.data import GROUND_TRUTH, SNAPSHOTS
from hindcast.event_mod import modulate_with_event
from hindcast.bridge import predict_bridge
from hindcast.commodity import predict_commodity
from hindcast.consult import SCHOOL_LABELS, consult
from hindcast.fx import predict_fx
from hindcast.policy_rate import predict_policy_rate
from hindcast.predict import predict
from hindcast.state import VARIABLES, StructuralState
from hindcast.treasury_yield import predict_yield as predict_treasury_yield

TODAY_KEY = "2026-05-14"

# ── 23-ADR 本周热点策展列表（人工维护，每周更新） ─────────────────────────────
# 硬阈值：影响 5000 万人 OR 单日资产波动 ≥1%（23-ADR §2）
WEEKLY_EVENTS = [
    {
        "id": "2026-06-fed-hold",
        "title": "美联储6月FOMC维持利率不变",
        "title_en": "Fed holds rates at June FOMC",
        "text": (
            "美联储联邦公开市场委员会（FOMC）2026年6月决定维持联邦基金利率目标区间不变。"
            "会后声明措辞较5月略偏鹰，鲍威尔在新闻发布会上表示「通胀回落速度仍不及预期」，"
            "但同时承认劳动力市场「已显示降温迹象」。点阵图显示2026年内降息次数中位数从2次降至1次。"
            "10年期美债收益率当日上行6bp，美元指数（DXY）上涨0.4%，黄金短暂下行后收平。"
        ),
        "as_of": "2026-06-12",
        "source": "Fed press release / Reuters",
    },
    {
        "id": "2026-06-us-china-tariff-reorg",
        "title": "美国宣布对华关税「重组」方案",
        "title_en": "US announces China tariff 'restructuring'",
        "text": (
            "美国贸易代表办公室（USTR）宣布对第三轮加征关税（约3600亿美元商品）启动「结构性重组」审查，"
            "拟将部分制造业关税从25%下调至15%，同时新增对中国半导体设备和AI芯片的出口管制扩大措施。"
            "中方商务部回应称「保留反制权利」，人民币离岸汇率（USD/CNH）当日贬值0.5%。"
            "分析人士解读不一：部分认为这是去风险化的阶段性缓和，部分认为技术围堵力度实质增强。"
        ),
        "as_of": "2026-06-10",
        "source": "USTR / WSJ / 财新",
    },
    {
        "id": "2026-06-ecb-cut",
        "title": "欧洲央行6月降息25bp",
        "title_en": "ECB cuts 25bp at June meeting",
        "text": (
            "欧洲中央银行管理委员会决定将三项关键利率各下调25个基点，为本轮降息周期第三次调整。"
            "拉加德行长表示欧元区通胀「正在按预期轨迹回落」，但强调未来路径仍「依赖数据」，"
            "反对市场对年内连续大幅降息的定价。欧元兑美元（EUR/USD）跌0.6%至1.08，"
            "德国10年期国债收益率下行4bp。能源价格上涨和南欧财政压力仍是主要下行风险。"
        ),
        "as_of": "2026-06-05",
        "source": "ECB press release / FT",
    },
]

app = FastAPI(
    title="Hindcast",
    description=(
        "经济推理的诚实实验室 — 呈现 4 个经济学派各自如何推理 + 诚实战绩 + 分歧。"
        "非预测器、非投资/配置建议（16/17/18-ADR 诚实边界）"
    ),
    version="0.5.0",
)

# CORS：允许前端（Vercel 静态站）跨域调用本后端（Render）。
# 用 ALLOWED_ORIGINS 环境变量（逗号分隔）收紧；默认 "*" 便于首次部署联通。
_origins_env = os.getenv("ALLOWED_ORIGINS", "*").strip()
_allowed_origins = ["*"] if _origins_env == "*" else [o.strip() for o in _origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent.parent.parent / "web"


# ── 18-ADR 诚实边界：产品对外只呈现"4 学派怎么推理 + 战绩 + 分歧"，
#    绝不作为配置/方向建议。此文案为服务端单一真相源，前端直接渲染。
HONEST_FRAME = {
    "not_advice": "仅供参考 · 非投资 / 资产配置建议",
    "negative_value_warning": (
        "经我们自己的诚实检验：作为方向预测器，对普通散户为负价值"
        "（跟随它调仓的诚实评分 42 ≪ 完全无视它、自己分散持有 76）。"
        "请勿据此买卖或调仓。"
    ),
    "what_we_deliver": (
        "本产品交付的是「4 个经济学派各自如何推理、它们的诚实历史战绩、"
        "以及它们在哪儿分歧」——方向由你自行判断。"
    ),
    "neutral_default": "没有明确大势 / 催化剂时，诚实的做法是：保持均衡，不动。",
    "ref": "依据 16 / 17 / 18-ADR 诚实边界",
}

# 英文版（默认语言）。内容与中文等价，18-ADR 边界不打折。
HONEST_FRAME_EN = {
    "not_advice": "For reference only · not investment / allocation advice",
    "negative_value_warning": (
        "By our own honest testing: as a direction predictor this engine has "
        "negative value for ordinary retail investors (an honest score of 42 "
        "for following its calls vs. 76 for ignoring it and simply holding a "
        "diversified mix). Do not buy, sell, or rebalance based on it."
    ),
    "what_we_deliver": (
        "What this product delivers: how each of 4 economic schools reasons, "
        "their honest historical track record, and where they disagree — the "
        "direction call is yours to make."
    ),
    "neutral_default": (
        "With no clear macro trend or catalyst, the honest stance is: "
        "stay balanced, do nothing."
    ),
    "ref": "Per the 16 / 17 / 18-ADR honesty boundary",
}

# 前端按 lang 取用；非破坏——旧 index.html 仍读顶层 honest_frame(zh)。
HONEST_FRAME_I18N = {"en": HONEST_FRAME_EN, "zh": HONEST_FRAME}


def _stance(forecast) -> dict:
    """从学派(不)一致派生『呈现态』。

    绝不声称 regime（事前 regime 分诊闸门 = 拱顶石，尚未构建，见 18-ADR §2.2）——
    仅如实反映 4 学派是否方向一致；不一致即"无明确方向 → 保持均衡"。
    """
    out: dict = {}
    for h, hf in forecast.horizons.items():
        consensus = forecast.is_unanimous and hf.dir in ("up", "down")
        up = hf.dir == "up"
        out[h] = {
            "label": (
                f"4 学派一致：{'看多' if up else '看空'}（研究记录，非建议）"
                if consensus
                else "无明确方向 → 保持均衡"
            ),
            "label_en": (
                f"4 schools agree: {'bullish' if up else 'bearish'} "
                "(research record, not advice)"
                if consensus
                else "No clear direction → stay balanced"
            ),
            "no_clear_direction": not consensus,
        }
    return out


def _stance_rate(forecast) -> dict:
    """Fed funds 决议型呈现态：无 horizons，按学派(不)一致 + aggregate_action 派生。

    绝不声称 regime（拱顶石未造）；仅如实反映 4 学派是否对下次 FOMC 行动一致。
    """
    act = getattr(forecast, "aggregate_action", None)
    uni = bool(getattr(forecast, "is_unanimous", False))
    name = {"hike": "预期加息", "cut": "预期降息", "hold": "预期按兵不动"}.get(
        act, "无明确共识"
    )
    name_en = {
        "hike": "expect a hike",
        "cut": "expect a cut",
        "hold": "expect a hold",
    }.get(act, "no clear consensus")
    consensus = uni and act in ("hike", "cut", "hold")
    return {
        "decision": {
            "label": (
                f"4 学派一致：{name}（研究记录，非建议）"
                if consensus
                else "学派分歧 → 无明确共识"
            ),
            "label_en": (
                f"4 schools agree: {name_en} (research record, not advice)"
                if consensus
                else "Schools split → no clear consensus"
            ),
            "no_clear_direction": not consensus,
        }
    }


def _with_honest(payload: dict, stance: dict) -> dict:
    """给多标的端点统一附 18-ADR 诚实框（服务端单一真相源；is_advice 恒 False）。"""
    payload["honest_frame"] = HONEST_FRAME
    payload["honest_frame_i18n"] = HONEST_FRAME_I18N
    payload["stance"] = stance
    payload["is_advice"] = False
    return payload


def _forecast_payload(forecast, *, ground_truth: dict | None = None) -> dict:
    """三个 predict 端点共用的返回体（含 18-ADR 诚实框 + 呈现态）。"""
    payload = {
        "as_of": forecast.as_of,
        "label": forecast.label,
        "asset": forecast.asset,
        "n_valid_schools": forecast.n_valid_schools,
        "is_unanimous": forecast.is_unanimous,
        "is_split": forecast.is_split,
        "horizons": {
            h: {
                "direction": hf.dir,
                "vote_counts": hf.vote_counts,
                "school_directions": hf.school_directions,
            }
            for h, hf in forecast.horizons.items()
        },
        "verdicts": [
            {
                "school": v.school,
                "verdict": {
                    h: {"dir": hz.dir, "range_pct": hz.range_pct}
                    for h, hz in v.verdict.items()
                },
                "top_signals": v.top_signals,
                "historical_precedents": v.historical_precedents,
                "volatility_class": v.volatility_class,
                "attribution_note": v.attribution_note,
                "reasoning": v.reasoning,
                "confidence": v.confidence,
                "failed": v._failed,
            }
            for v in forecast.verdicts
        ],
        # 18-ADR：诚实框 + 呈现态（服务端单一真相源；is_advice 恒 False）
        "honest_frame": HONEST_FRAME,
        "honest_frame_i18n": HONEST_FRAME_I18N,
        "stance": _stance(forecast),
        "is_advice": False,
    }
    # v0.5.6: 第 5 派制度政治经济学派的独立简报 (不投票, 仅作为参考喂给 4 经济派)
    if getattr(forecast, "political_brief", None):
        payload["political_brief"] = forecast.political_brief
    if ground_truth is not None:
        payload["ground_truth"] = ground_truth
    return payload


@app.get("/api/snapshots")
def get_snapshots():
    """列出所有可用的历史时点。"""
    return [
        {
            "as_of": snap.as_of,
            "label": snap.label,
            "event": GROUND_TRUTH.get(snap.as_of, {}).get("event", ""),
            "ground_truth_t5": GROUND_TRUTH.get(snap.as_of, {}).get("T+5", {}),
            "ground_truth_t20": GROUND_TRUTH.get(snap.as_of, {}).get("T+20", {}),
        }
        for snap in SNAPSHOTS.values()
    ]


@app.get("/api/state/{date}")
def get_state(date: str):
    """拿某日的 15 变量结构状态。"""
    snap = SNAPSHOTS.get(date)
    if not snap:
        raise HTTPException(
            status_code=404,
            detail=f"No snapshot for {date}. Available: {list(SNAPSHOTS.keys())}",
        )
    return {
        "as_of": snap.as_of,
        "label": snap.label,
        "variables": [
            {
                "id": var_id,
                "name": var.name,
                "value": snap.values.get(var_id),
                "school_relevance": var.school_relevance,
            }
            for var_id, var in VARIABLES.items()
        ],
    }


@app.post("/api/predict/{date}")
def post_predict(date: str, priors: BridgePriorsBody | None = None):
    """跑 4 学派常态预测 + 多数投票。~$0.02, 30-60s。

    可选 priors body 注入桥梁变量预测 (TIPS/BEI/DXY) → XAU 集成预测。
    """
    snap = SNAPSHOTS.get(date)
    if not snap:
        raise HTTPException(
            status_code=404,
            detail=f"No snapshot for {date}",
        )
    bridge_priors = priors.bridge_priors if priors else None
    forecast = predict(snap, bridge_priors=bridge_priors)
    return _forecast_payload(forecast, ground_truth=GROUND_TRUTH.get(date, {}))


@app.get("/api/today")
def get_today():
    """🔮 实时模拟基线——返回 today (2026-05-14) 的结构状态。"""
    snap = SNAPSHOTS.get(TODAY_KEY)
    if not snap:
        raise HTTPException(status_code=500, detail=f"No today snapshot ({TODAY_KEY})")
    return {
        "as_of": snap.as_of,
        "label": snap.label,
        "variables": [
            {
                "id": var_id,
                "name": var.name,
                "value": snap.values.get(var_id),
                "school_relevance": var.school_relevance,
            }
            for var_id, var in VARIABLES.items()
        ],
    }


class CustomStateRequest(BaseModel):
    as_of: str = Field(default_factory=lambda: TODAY_KEY)
    label: str = "用户自定义状态"
    values: dict[str, float]


class BridgePriorsBody(BaseModel):
    """XAU prior injection — 用户在客户端记录的桥梁变量预测."""
    bridge_priors: dict[str, dict] | None = None  # {"tips": {"t5":"down","t20":"down","label":"..."}, ...}


@app.post("/api/predict-custom")
def post_predict_custom(req: CustomStateRequest):
    """🔮 跑任意结构状态下的 4 学派常态预测（实时模拟核心）。"""
    snap = StructuralState(as_of=req.as_of, label=req.label, values=req.values)
    forecast = predict(snap)
    return _forecast_payload(forecast)


class EventRequest(BaseModel):
    values: dict[str, float]
    event_text: str
    as_of: str = Field(default_factory=lambda: TODAY_KEY)
    label: str = "用户自定义状态"


@app.post("/api/predict-with-event")
def post_predict_with_event(req: EventRequest):
    """🟧 事件修正：在常态预测之上叠加新闻事件 → 4 学派给 delta。

    返回 baseline (常态) + modulation (修正 delta) + final_path (合成)。
    """
    snap = StructuralState(as_of=req.as_of, label=req.label, values=req.values)

    # Step 1: 常态预测（baseline）
    forecast = predict(snap)

    # Step 2: 事件修正
    modulation = modulate_with_event(snap, req.event_text)

    return {
        "as_of": snap.as_of,
        "event_text": req.event_text,
        # 18-ADR：诚实框 + 呈现态（与常态预测端点一致的单一真相源）
        "honest_frame": HONEST_FRAME,
        "honest_frame_i18n": HONEST_FRAME_I18N,
        "stance": _stance(forecast),
        "is_advice": False,
        "baseline": {
            "horizons": {
                h: {
                    "direction": hf.dir,
                    "vote_counts": hf.vote_counts,
                }
                for h, hf in forecast.horizons.items()
            },
            "verdicts": [
                {
                    "school": v.school,
                    "verdict": {
                        h: {"dir": hz.dir, "range_pct": hz.range_pct}
                        for h, hz in v.verdict.items()
                    },
                    "top_signals": v.top_signals,
                    "volatility_class": v.volatility_class,
                    "attribution_note": v.attribution_note,
                    "reasoning": v.reasoning,
                    "failed": v._failed,
                }
                for v in forecast.verdicts
            ],
        },
        "modulation": {
            "structural_change_votes": modulation.structural_change_votes,
            "aggregate_delta": modulation.aggregate,
            "deltas": [
                {
                    "school": d.school,
                    "delta": {
                        h: {"adjust_pct": hz.adjust_pct, "reason": hz.reason}
                        for h, hz in d.delta_to_steady_state.items()
                    },
                    "event_volatility_class": d.event_volatility_class,
                    "event_attribution_note": d.event_attribution_note,
                    "is_structural_change": d.is_structural_change,
                    "structural_impact_note": d.structural_impact_note,
                    "amplifies": d.amplifies,
                    "confidence": d.confidence,
                    "failed": d._failed,
                }
                for d in modulation.deltas
            ],
        },
    }


class ConsultRequest(BaseModel):
    """C 端咨询请求（18-ADR ③）。与预测端点物理隔离，不回流账本/理论。"""
    school: str
    question: str
    context: str = ""


@app.post("/api/consult")
def post_consult(req: ConsultRequest):
    """💬 C 端咨询：用户点进某学派追问。章程绑定——只深讲推理+战绩+盲区，
    硬禁买卖/配置指令（boundary 同时由 consult.py 系统提示词与本响应横幅双重兜底）。

    刻意不调用 _forecast_payload / 账本 / 理论拟合层（数据防火墙）。
    """
    if req.school not in SCHOOL_LABELS:
        raise HTTPException(status_code=400, detail=f"未知学派: {req.school}")
    answer = consult(req.school, req.question, req.context)
    return {
        "school": req.school,
        "school_label": SCHOOL_LABELS[req.school],
        "answer": answer,
        "honest_frame": HONEST_FRAME,
        "honest_frame_i18n": HONEST_FRAME_I18N,
        "is_advice": False,
    }


@app.post("/api/predict-bridge/{date}")
def post_predict_bridge(date: str, target: str = "DXY"):
    """🌉 桥梁变量预测 (XAU 集成预测必备). target=US_10Y_TIPS | US_10Y_BEI | DXY"""
    if target not in ("US_10Y_TIPS", "US_10Y_BEI", "DXY"):
        raise HTTPException(status_code=400, detail=f"target must be US_10Y_TIPS|US_10Y_BEI|DXY")
    snap = SNAPSHOTS.get(date)
    if not snap:
        raise HTTPException(status_code=404, detail=f"No snapshot for {date}")
    if snap.macro is None:
        raise HTTPException(status_code=422, detail=f"No macro data for {date}")
    forecast = predict_bridge(snap, target)  # type: ignore[arg-type]
    from hindcast.data import BRIDGE_GROUND_TRUTH
    gt = BRIDGE_GROUND_TRUTH.get(date, {}).get(target, {})
    return _with_honest({
        "as_of": forecast.as_of, "label": forecast.label, "target": forecast.target,
        "current_value": forecast.current_value,
        "n_valid_schools": forecast.n_valid,
        "is_unanimous": forecast.is_unanimous,
        "horizons": {
            h: {"direction": hf.dir, "vote_counts": hf.vote_counts,
                "school_directions": hf.school_directions}
            for h, hf in forecast.horizons.items()
        },
        "verdicts": [
            {
                "school": v.school, "target": v.target,
                "verdict": {h: {"dir": hz.dir, "range_pct": hz.range_bps}  # 复用 forecast UI shape
                            for h, hz in v.verdict.items()},
                "top_signals": v.top_signals,
                "volatility_class": v.volatility_class,
                "attribution_note": v.attribution_note,
                "reasoning": v.reasoning, "confidence": v.confidence,
                "failed": v._failed,
            } for v in forecast.verdicts
        ],
        "ground_truth": gt,
    }, _stance(forecast))


@app.post("/api/predict-fx/{date}")
def post_predict_fx(date: str, target: str = "USD/CNH"):
    """💱 跑 4 学派对 FX T+5/T+20 方向的预测。target=USD/CNH | USD/JPY"""
    if target not in ("USD/CNH", "USD/JPY"):
        raise HTTPException(status_code=400, detail=f"target must be USD/CNH or USD/JPY")
    snap = SNAPSHOTS.get(date)
    if not snap:
        raise HTTPException(status_code=404, detail=f"No snapshot for {date}")
    if snap.macro is None:
        raise HTTPException(status_code=422, detail=f"No macro data for {date}")
    forecast = predict_fx(snap, target)  # type: ignore[arg-type]
    from hindcast.data import FX_GROUND_TRUTH
    gt = FX_GROUND_TRUTH.get(date, {}).get(target, {})
    return _with_honest({
        "as_of": forecast.as_of, "label": forecast.label, "target": forecast.target,
        "current_spot": forecast.current_spot,
        "taylor_differential": forecast.taylor_differential,
        "n_valid_schools": forecast.n_valid,
        "is_unanimous": forecast.is_unanimous,
        "horizons": {
            h: {"direction": hf.dir, "vote_counts": hf.vote_counts,
                "school_directions": hf.school_directions}
            for h, hf in forecast.horizons.items()
        },
        "verdicts": [
            {
                "school": v.school, "target": v.target,
                "verdict": {h: {"dir": hz.dir, "range_pct": hz.range_pct}
                            for h, hz in v.verdict.items()},
                "top_signals": v.top_signals,
                "taylor_diff_signal": v.taylor_diff_signal,
                "volatility_class": v.volatility_class,
                "attribution_note": v.attribution_note,
                "reasoning": v.reasoning, "confidence": v.confidence,
                "failed": v._failed,
            } for v in forecast.verdicts
        ],
        "ground_truth": gt,
    }, _stance(forecast))


@app.post("/api/predict-commodity/{date}")
def post_predict_commodity(date: str, target: str = "CRUDE_OIL"):
    """🛢️ 跑 4 学派对商品 T+5/T+20 方向的预测。target=CRUDE_OIL | COPPER"""
    if target not in ("CRUDE_OIL", "COPPER"):
        raise HTTPException(status_code=400, detail=f"target must be CRUDE_OIL or COPPER")
    snap = SNAPSHOTS.get(date)
    if not snap:
        raise HTTPException(status_code=404, detail=f"No snapshot for {date}")
    if snap.macro is None:
        raise HTTPException(status_code=422, detail=f"No macro data for {date}")
    forecast = predict_commodity(snap, target)  # type: ignore[arg-type]
    from hindcast.data import COMMODITY_GROUND_TRUTH
    gt = COMMODITY_GROUND_TRUTH.get(date, {}).get(target, {})
    return _with_honest({
        "as_of": forecast.as_of, "label": forecast.label, "target": forecast.target,
        "current_price": forecast.current_price,
        "n_valid_schools": forecast.n_valid,
        "is_unanimous": forecast.is_unanimous,
        "horizons": {
            h: {"direction": hf.dir, "vote_counts": hf.vote_counts,
                "school_directions": hf.school_directions}
            for h, hf in forecast.horizons.items()
        },
        "verdicts": [
            {
                "school": v.school, "target": v.target,
                "verdict": {h: {"dir": hz.dir, "range_pct": hz.range_pct}
                            for h, hz in v.verdict.items()},
                "top_signals": v.top_signals,
                "supply_demand_signal": v.supply_demand_signal,
                "volatility_class": v.volatility_class,
                "attribution_note": v.attribution_note,
                "reasoning": v.reasoning, "confidence": v.confidence,
                "failed": v._failed,
            } for v in forecast.verdicts
        ],
        "ground_truth": gt,
    }, _stance(forecast))


@app.post("/api/predict-yield/{date}")
def post_predict_yield(date: str, target: str = "US_2Y"):
    """📈 跑 4 学派对国债收益率 T+5/T+20 方向的预测。target=US_2Y|US_10Y"""
    if target not in ("US_2Y", "US_10Y"):
        raise HTTPException(status_code=400, detail=f"target must be US_2Y or US_10Y, got {target}")
    snap = SNAPSHOTS.get(date)
    if not snap:
        raise HTTPException(status_code=404, detail=f"No snapshot for {date}")
    if snap.macro is None:
        raise HTTPException(status_code=422, detail=f"No macro data for {date}")
    forecast = predict_treasury_yield(snap, target)  # type: ignore[arg-type]

    from hindcast.data import YIELD_GROUND_TRUTH
    gt = YIELD_GROUND_TRUTH.get(date, {}).get(target, {})

    return _with_honest({
        "as_of": forecast.as_of,
        "label": forecast.label,
        "target": forecast.target,
        "current_yield": forecast.current_yield,
        "n_valid_schools": forecast.n_valid,
        "is_unanimous": forecast.is_unanimous,
        "is_split": forecast.is_split,
        "horizons": {
            h: {"direction": hf.dir, "vote_counts": hf.vote_counts,
                "school_directions": hf.school_directions}
            for h, hf in forecast.horizons.items()
        },
        "verdicts": [
            {
                "school": v.school, "target": v.target,
                "verdict": {h: {"dir": hz.dir, "range_bps": hz.range_bps}
                            for h, hz in v.verdict.items()},
                "top_signals": v.top_signals,
                "yield_curve_signal": v.yield_curve_signal,
                "volatility_class": v.volatility_class,
                "attribution_note": v.attribution_note,
                "reasoning": v.reasoning,
                "confidence": v.confidence,
                "failed": v._failed,
            }
            for v in forecast.verdicts
        ],
        "ground_truth": gt,
    }, _stance(forecast))


@app.post("/api/predict-rate/{date}")
def post_predict_rate(date: str):
    """🏦 跑 4 学派对 Fed funds rate 下次 FOMC 决议的预测。"""
    snap = SNAPSHOTS.get(date)
    if not snap:
        raise HTTPException(status_code=404, detail=f"No snapshot for {date}")
    if snap.macro is None:
        raise HTTPException(status_code=422, detail=f"No macro data for {date} — Fed funds prediction requires CPI / unemployment / output gap")
    forecast = predict_policy_rate(snap)
    return _with_honest({
        "as_of": forecast.as_of,
        "label": forecast.label,
        "target": forecast.target,
        "current_fed_funds": forecast.current_fed_funds,
        "taylor_implied": forecast.taylor_implied,
        "n_valid_schools": forecast.n_valid,
        "is_unanimous": forecast.is_unanimous,
        "is_split": forecast.is_split,
        "aggregate_action": forecast.aggregate_action,
        "aggregate_bps": forecast.aggregate_bps,
        "vote_counts": forecast.vote_counts,
        "verdicts": [
            {
                "school": v.school,
                "action": v.action,
                "bps": v.bps,
                "next_fomc_horizon_days": v.next_fomc_horizon_days,
                "top_signals": v.top_signals,
                "taylor_implied_anchor": v.taylor_implied_anchor,
                "volatility_class": v.volatility_class,
                "attribution_note": v.attribution_note,
                "reasoning": v.reasoning,
                "confidence": v.confidence,
                "failed": v._failed,
            }
            for v in forecast.verdicts
        ],
    }, _stance_rate(forecast))


class CustomPolicyRateRequest(BaseModel):
    as_of: str = Field(default_factory=lambda: TODAY_KEY)
    label: str = "用户自定义"
    values: dict[str, float]
    macro: dict


@app.post("/api/predict-rate-custom")
def post_predict_rate_custom(req: CustomPolicyRateRequest):
    """🏦 任意 state + macro → Fed funds 预测（实时模拟）。"""
    from hindcast.state import MacroEconomic
    macro = MacroEconomic(**req.macro)
    snap = StructuralState(as_of=req.as_of, label=req.label, values=req.values, macro=macro)
    forecast = predict_policy_rate(snap)
    return _with_honest({
        "as_of": forecast.as_of, "label": forecast.label, "target": forecast.target,
        "current_fed_funds": forecast.current_fed_funds, "taylor_implied": forecast.taylor_implied,
        "n_valid_schools": forecast.n_valid,
        "is_unanimous": forecast.is_unanimous, "is_split": forecast.is_split,
        "aggregate_action": forecast.aggregate_action, "aggregate_bps": forecast.aggregate_bps,
        "vote_counts": forecast.vote_counts,
        "verdicts": [
            {
                "school": v.school, "action": v.action, "bps": v.bps,
                "next_fomc_horizon_days": v.next_fomc_horizon_days,
                "top_signals": v.top_signals, "taylor_implied_anchor": v.taylor_implied_anchor,
                "volatility_class": v.volatility_class, "attribution_note": v.attribution_note,
                "reasoning": v.reasoning, "confidence": v.confidence, "failed": v._failed,
            }
            for v in forecast.verdicts
        ],
    }, _stance_rate(forecast))


# ── C：gap 差值数据（研究/展示，只读）。单向墙安全：GET、非 ex-ante 输入，
#    gap 绝不回流任何决策（19/20-ADR）。诚实边界随数据不可拆出。 ──
GAP_BOUNDARY = {
    "red_line": {
        "zh": "这是研究 / 数据，不是预测信号；任何「用 gap 预测 / 择时」明令禁止；gap 绝不回流任何决策（单向墙）。",
        "en": "Research/data, NOT a prediction signal. Any 'use gap to predict/time' use is forbidden; gap never flows back into any decision (one-way wall).",
    },
    "coverage": {
        "zh": "覆盖起点逐序列不同；早于起点 = 无 vintage，留白、不以修订值顶替（规矩A）。",
        "en": "Coverage start differs per series; before it = no vintage, left blank, not substituted (Rule A).",
    },
    "power": {
        "zh": "n≈12（TFP=2）→ 方向性 / 量级感，非统计置信。",
        "en": "n≈12 (TFP=2) → directional / order-of-magnitude only, not statistical confidence.",
    },
    "no_cross": {
        "zh": "(b) 类各自原单位，不可跨序列比大小。",
        "en": "(b)-tier are in their own units; do NOT compare magnitudes across series.",
    },
    "not_conflate": {
        "zh": "勿与 #1 的 67.9% 混引（口径不同）。",
        "en": "Do not conflate with the 67.9% from #1 (different measurement).",
    },
}


@app.get("/api/gap")
def get_gap():
    """C 交付：gap 差值数据集（首发布 vs 今）。只读研究展示，非预测信号、不回流决策。"""
    import json as _json

    raw = _json.loads(
        (Path(__file__).parent / "data" / "gap_dataset_step1.json").read_text(
            encoding="utf-8"
        )
    )
    a, b, c = [], [], []
    for var, v in raw.items():
        row = {
            "var": var,
            "mean_abs_gap": v["mean_abs_gap"],
            "max_abs_gap": v["max_abs_gap"],
            "unit": v["unit"],
            "first_vintage": v["first_vintage"],
            "n": v["n"],
        }
        if "yoy" in v["unit"]:
            a.append(row)
        elif var in ("us_potential_gdp", "us_tfp") or v["n"] <= 2:
            c.append({"var": var, "unit": v["unit"],
                      "why_excluded": "单位/换基混淆或样本过薄，不作修订幅度用"})
        else:
            b.append(row)
    g = raw.get("us_gdp_yoy", {})
    return {
        "headline": {
            "zh": f"GDP 增速事后平均被改写 {g.get('mean_abs_gap',0):.2f} 个百分点"
                  f"（最大 {g.get('max_abs_gap',0):.2f}）——当时看到的，与今天史书上的，系统性不同。",
            "en": f"GDP growth was revised {g.get('mean_abs_gap',0):.2f}pp on average "
                  f"after the fact (max {g.get('max_abs_gap',0):.2f}) — what was seen "
                  f"then differs systematically from today's history books.",
        },
        "tier_a": a,   # yoy 量级可信
        "tier_b": b,   # 各原单位，不可横比
        "tier_c": c,   # 不作修订幅度用
        "boundary": GAP_BOUNDARY,
        "research_only": True,
        "is_advice": False,
    }


# ── "事后诸葛亮" · 当时数据 vs 修订数据 + 走偏的圆场。仅展示/教学层；
#    凡 LLM 计算均预算到 data/then_vs_now.json，运行时只读、不调 LLM。
#    数据源声明：structural_asof 是 RAG 未接入 live 的"近似锚点"模块，
#    仅用于本演示，**未改 live build_state_asof**（A+C "不接 live" 决定不破）。 ──
@app.get("/api/then-vs-now")
def get_then_vs_now():
    """读 data/then_vs_now.json，返回所有锚点的两遍对照 + 圆场。
    单向墙：vintage=Pass1 标'当时'、revised=Pass2 标'今天'、标签清楚。
    无 LLM、无 ex-ante 输入；is_advice=False；展示教学用。
    """
    import json as _json
    p = Path(__file__).parent / "data" / "then_vs_now.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="then_vs_now.json 未生成（跑 scripts/build_then_vs_now.py）")
    anchors = _json.loads(p.read_text(encoding="utf-8"))
    return {
        "anchors": anchors,
        "honest_frame": HONEST_FRAME,
        "honest_frame_i18n": HONEST_FRAME_I18N,
        "is_advice": False,
        "research_only": True,
        "demo_note": {
            "zh": "Pass1 用当时官方第一次公布的数据 / 近似锚点（structural_asof，非精确真值）；"
                  "Pass2 用今天修订后的数据（手搭）。差异 = 实时认知 vs 事后回看的活演示。"
                  "经济学派事后才能自圆其说——这是教学/娱乐，不是预测。",
            "en": "Pass 1 uses first-print data + coarse approximate anchors (structural_asof, "
                  "not precise truth). Pass 2 uses today's revised view (curated). The difference "
                  "is a live demo of real-time perception vs hindsight. Economists rationalize only "
                  "after the fact — this is education/entertainment, not prediction.",
        },
    }


@app.get("/")
def root():
    """单页前端：默认服 index-v2.html (含 Fed funds target selector)，回退到 index.html。"""
    v2 = STATIC_DIR / "index-v2.html"
    v1 = STATIC_DIR / "index.html"
    if v2.exists():
        return FileResponse(v2)
    if v1.exists():
        return FileResponse(v1)
    raise HTTPException(status_code=500, detail=f"No index.html or index-v2.html in {STATIC_DIR}")


@app.get("/v1")
def root_v1():
    """旧版 v1 入口（参照对比用）。"""
    v1 = STATIC_DIR / "index.html"
    if not v1.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(v1)


@app.get("/echoes")
def root_echoes():
    """历史回响入口 (Hindcast Echoes)."""
    p = STATIC_DIR / "echoes.html"
    if not p.exists():
        raise HTTPException(status_code=404, detail="echoes.html not found")
    return FileResponse(p)


@app.get("/pretext.js")
def serve_pretext():
    """Pretext 库（v2 用）。"""
    p = STATIC_DIR / "pretext.js"
    if not p.exists():
        raise HTTPException(status_code=404, detail="pretext.js not found")
    return FileResponse(p, media_type="application/javascript")


@app.get("/api/weekly-events")
def get_weekly_events():
    """📰 本周热点策展列表 (23-ADR · 人工维护 · 每周更新)."""
    return WEEKLY_EVENTS


class NarrativeRequest(BaseModel):
    text: str
    as_of: str
    mode: str = "current"


def _session_payload(session: object) -> dict:
    """序列化 NarrativeSession → dict (JSON 可序列化)."""
    from hindcast.narrative_types import NarrativeSession
    s: NarrativeSession = session  # type: ignore[assignment]
    return {
        "event": {
            "text": s.event.text,
            "as_of": s.event.as_of,
            "mode": s.event.mode,
        },
        "outputs": [
            {
                "lens_id": o.lens_id,
                "discipline": o.discipline,
                "label_zh": o.label_zh,
                "label_en": o.label_en,
                "raw": o.raw,
                "failed": o.failed,
                "error": o.error,
            }
            for o in s.outputs
        ],
        "router": {
            "selected_disciplines": s.router.selected_disciplines,
            "exempted_default": s.router.exempted_default,
            "reasoning": s.router.reasoning,
        } if s.router else None,
        "disciplines_called": list(dict.fromkeys(o.discipline for o in s.outputs)),
        "rag_case_id": s.rag_case_id,
        "rag_case_label": s.rag_case_label,
    }


@app.post("/api/narrative")
def post_narrative(req: NarrativeRequest):
    """🧠 叙事模拟 chain (22-ADR).

    接受事件文本 + 日期 → 历史 2 派 → router → 制度/物质/心理文化层 → 中枢大脑.
    ~30-90s, ~$0.08. 不出方向/幅度, 非投资建议 (21-ADR).
    """
    from hindcast.chain import run_narrative_chain
    from hindcast.narrative_types import NarrativeEvent

    event = NarrativeEvent(
        text=req.text,
        as_of=req.as_of,
        mode=req.mode,  # type: ignore[arg-type]
    )
    session = run_narrative_chain(event)
    return _session_payload(session)


# ── 历史回响 (Hindcast Echoes) — 热点种子列表 ────────────────────────────────
SEED_TRENDING = [
    {
        "id": "2026-06-us-china-tariff",
        "title": "美国对华关税全面升级",
        "blurb": "USTR 宣布对 3600 亿美元商品启动「结构性重组」，半导体出口管制同步扩大",
        "as_of": "2026-06-10",
    },
    {
        "id": "2026-06-fed-hold",
        "title": "美联储维持利率不变，点阵图转鹰",
        "blurb": "FOMC 2026 年 6 月按兵不动，鲍威尔称「通胀回落速度仍不及预期」",
        "as_of": "2026-06-12",
    },
    {
        "id": "2026-06-ecb-cut",
        "title": "欧洲央行第三次降息 25bp",
        "blurb": "欧元区通胀「按预期轨迹回落」，但南欧财政压力与能源价格构成下行风险",
        "as_of": "2026-06-05",
    },
    {
        "id": "2026-06-ai-regulation",
        "title": "欧盟 AI 法案首批执法启动",
        "blurb": "高风险 AI 系统监管落地，大模型提供商须提交透明度报告，违规最高罚款营收 7%",
        "as_of": "2026-06-01",
    },
    {
        "id": "2026-05-japan-boj-hike",
        "title": "日本央行再度加息至 0.75%",
        "blurb": "日元升值压力与出口竞争力之间的政策两难，失业率维持 2.5% 近历史低位",
        "as_of": "2026-05-28",
    },
    {
        "id": "2026-05-india-election",
        "title": "印度大选后经济政策转向",
        "blurb": "新政府优先扩张基础设施支出，外资政策趋于收紧，「印度制造」替代战略加速",
        "as_of": "2026-05-20",
    },
    {
        "id": "2026-05-oil-opec-cut",
        "title": "OPEC+ 宣布额外减产 100 万桶/日",
        "blurb": "沙特主导超预期减产，布油反弹至 82 美元，全球通胀二次上行风险升温",
        "as_of": "2026-05-15",
    },
    {
        "id": "2026-04-dollar-reserve-shift",
        "title": "美元全球储备占比跌破 57%",
        "blurb": "IMF 季度报告显示人民币、欧元份额继续上升，美元霸权结构性侵蚀持续",
        "as_of": "2026-04-30",
    },
]


class LifeReportRequest(BaseModel):
    text: str
    as_of: str = "2026-06-18"
    mode: str = "current"


@app.get("/api/trending")
def get_trending():
    """📰 历史回响热点 feed.

    v2: 实时新闻（Google News + BBC RSS）→ LLM 策展 + 生活维度打标（服务端缓存 30min）.
    网络/LLM 失败 → graceful fallback 到内置种子列表 SEED_TRENDING.
    """
    try:
        from hindcast.news_feed import build_trending_feed
        feed = build_trending_feed()
        if feed:
            return {"events": feed, "live": True}
    except Exception:
        pass
    # 兜底：给种子补默认生活维度，保证看板可渲染
    seeds = []
    for s in SEED_TRENDING:
        seeds.append({
            **s,
            "blurb": s.get("blurb", ""),
            "source": "内置种子",
            "primary": "power",
            "dimensions": ["power", "wallet"],
            "why_dim": "",
        })
    return {"events": seeds, "live": False}


@app.get("/api/heat")
def get_heat(q: str):
    """📈 某话题近 14 天新闻量曲线（GDELT timelinevol）→ 前端 sparkline.

    lazy 按需调用（GDELT 限流 1 req/5s）；失败返回空 points.
    """
    try:
        from hindcast.news_feed import fetch_heat
        return {"points": fetch_heat(q)}
    except Exception:
        return {"points": []}


@app.get("/api/glossary")
def get_glossary():
    """📖 名词解释静态词典（人工策展，零 AI 生成）→ 前端正文匹配 + 点击弹窗."""
    from hindcast.glossary import all_terms
    return all_terms()


@app.post("/api/life-report")
def post_life_report(req: LifeReportRequest):
    """🪞 历史回响生活报告 (Hindcast Echoes).

    接受事件文本 → 9-lens 叙事 chain → 翻译层 → LifeReport JSON.
    ~35–100s. 返回 6 张生活影响卡 + 镜像 + 学派吵架. 非投资建议 (21-ADR).
    """
    from hindcast.chain import run_narrative_chain
    from hindcast.narrative_types import NarrativeEvent
    from hindcast.translator import build_life_report

    event = NarrativeEvent(
        text=req.text,
        as_of=req.as_of,
        mode=req.mode,  # type: ignore[arg-type]
    )
    session = run_narrative_chain(event)
    return build_life_report(session)


def main():
    """Entry point for `hindcast web` CLI sub-command."""
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(prog="hindcast web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    print(f"\n🚀 Hindcast Web 启动在 http://{args.host}:{args.port}")
    print(f"   API docs: http://{args.host}:{args.port}/docs")
    print()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
