"""Hindcast · 鉴往 — Multi-school macro forecaster.

Public API:
    predict(state, asset='XAU/USD', horizons=['T+5','T+20']) → Forecast
    backtest(events) → BacktestReport

For details see 01-PRODUCT-DESIGN-v0.4.md and 09-ADR-PURE-VOTING-MVP.md.
"""

from hindcast.predict import Forecast, predict
from hindcast.state import (
    SCHOOLS,
    StructuralState,
    StructuralVariable,
    VARIABLES,
)
from hindcast.agents import Verdict

__version__ = "0.5.0"

__all__ = [
    "predict",
    "Forecast",
    "StructuralState",
    "StructuralVariable",
    "Verdict",
    "VARIABLES",
    "SCHOOLS",
]
