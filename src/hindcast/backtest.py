"""历史回测——对历史时点跑 predict()，对照 ground truth 算命中率。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from hindcast.data import ALL_SNAPSHOTS, GROUND_TRUTH
from hindcast.predict import Forecast, predict
from hindcast.state import StructuralState


class TimepointResult(BaseModel):
    forecast: Forecast
    ground_truth: dict
    hits: dict[str, bool]                  # horizon → hit

    @property
    def n_horizons(self) -> int:
        return len(self.hits)

    @property
    def n_hits(self) -> int:
        return sum(self.hits.values())


class BacktestReport(BaseModel):
    results: list[TimepointResult] = Field(default_factory=list)

    @property
    def total_hits(self) -> int:
        return sum(r.n_hits for r in self.results)

    @property
    def total_horizons(self) -> int:
        return sum(r.n_horizons for r in self.results)

    @property
    def hit_rate(self) -> float:
        if not self.total_horizons:
            return 0.0
        return self.total_hits / self.total_horizons

    def pretty(self) -> str:
        lines = [
            f"{'时点':<32} {'T+5 pred':<10} {'T+5 actual':<12} {'hit':<5} {'T+20 pred':<11} {'T+20 actual':<13} {'hit'}",
            "-" * 100,
        ]
        for r in self.results:
            row = [f"{r.forecast.label:<32}"]
            for h in ("T+5", "T+20"):
                pred = r.forecast.horizons[h].dir
                actual = r.ground_truth.get(h, {}).get("dir", "?")
                hit = r.hits.get(h, False)
                mark = "✅" if hit else "❌"
                if h == "T+5":
                    row.append(f"{pred:<10} {actual:<12} {mark:<5}")
                else:
                    row.append(f"{pred:<11} {actual:<13} {mark}")
            lines.append(" ".join(row))
        lines.append("-" * 100)
        lines.append(
            f"合计命中率: {self.total_hits}/{self.total_horizons} = {self.hit_rate*100:.0f}%"
        )
        lines.append(f"W3 hard gate 标准: ≥ 60%")
        lines.append(f"结果: {'✅ PASS' if self.hit_rate >= 0.6 else '❌ FAIL'}")
        return "\n".join(lines)


def run_backtest(
    snapshots: list[StructuralState] | None = None,
    horizons: list[str] | None = None,
) -> BacktestReport:
    """对历史时点跑回测。默认用全部内置 snapshot。"""
    snapshots = snapshots or ALL_SNAPSHOTS
    horizons = horizons or ["T+5", "T+20"]
    results: list[TimepointResult] = []

    for snap in snapshots:
        print(f"\n========== {snap.label} ({snap.as_of}) ==========")
        forecast = predict(snap, horizons=horizons)
        for v in forecast.verdicts:
            if v._failed:
                print(f"  {v.school:<25} FAILED — {v._error}")
            else:
                t5 = v.verdict.get("T+5")
                t20 = v.verdict.get("T+20")
                print(f"  {v.school:<25} T+5: {t5.dir:<5} T+20: {t20.dir:<5}")

        gt = GROUND_TRUTH.get(snap.as_of, {})
        hits = {
            h: forecast.horizons[h].dir == gt.get(h, {}).get("dir")
            for h in horizons
        }
        results.append(TimepointResult(forecast=forecast, ground_truth=gt, hits=hits))

    return BacktestReport(results=results)
