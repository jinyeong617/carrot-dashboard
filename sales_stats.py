"""
Statistical helpers for sales dashboards: hypothesis framing and standard tests.

Uses nonparametric tests where possible (skewed revenue is common).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class HypothesisTestResult:
    """One test outcome suitable for an executive + analyst audience."""

    title: str
    null_hypothesis: str
    method: str
    statistic: float | None
    p_value: float | None
    alpha: float
    conclusion_ko: str
    detail_ko: str
    extra: dict[str, Any] | None = None


def _fmt_p(p: float | None) -> str:
    if p is None or np.isnan(p):
        return "계산 불가"
    if p < 1e-4:
        return "< 0.0001"
    return f"{p:.4f}"


def daily_totals_from_raw(df: pd.DataFrame) -> pd.DataFrame:
    """One row per calendar date with total revenue."""
    out = df.groupby("날짜", as_index=False)["매출"].sum().sort_values("날짜")
    return out


def test_weekday_effect(daily_totals: pd.DataFrame) -> HypothesisTestResult:
    """
    Kruskal–Wallis H: do daily totals differ by weekday (요일)?
    Needs at least 2 days per weekday for stable groups.
    """
    d = daily_totals.copy()
    d["요일"] = d["날짜"].dt.day_name()
    order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    d["요일"] = pd.Categorical(d["요일"], categories=order, ordered=True)
    groups = [
        g["매출"].values
        for _, g in d.groupby("요일", observed=True)
        if len(g) >= 2
    ]
    if len(groups) < 2:
        return HypothesisTestResult(
            title="요일별 매출 차이",
            null_hypothesis="요일에 관계없이 일별 총매출 분포는 같다.",
            method="Kruskal–Wallis (비모수)",
            statistic=None,
            p_value=None,
            alpha=0.05,
            conclusion_ko="요일별로 비교할 만큼의 일수가 부족합니다.",
            detail_ko="각 요일에 최소 2일 이상의 데이터가 있어야 검정이 의미 있습니다.",
        )
    stat, p = stats.kruskal(*groups)
    reject = p < 0.05
    conclusion = (
        "요일에 따라 일별 총매출 분포가 통계적으로 다릅니다 (유의수준 5%)."
        if reject
        else "요일별 총매출 분포 차이를 5% 유의수준에서 뒷받침할 근거는 충분하지 않습니다."
    )
    medians = d.groupby("요일", observed=True)["매출"].median()
    best = medians.idxmax()
    detail = (
        f"p-value = {_fmt_p(p)}. "
        f"요일별 일별 총매출 중앙값이 가장 높은 요일: {best}. "
        "이 검정은 '평균이 다른가'가 아니라 분포/순위 차이를 봅니다."
    )
    return HypothesisTestResult(
        title="요일별 매출 차이",
        null_hypothesis="요일에 관계없이 일별 총매출 분포는 같다.",
        method="Kruskal–Wallis",
        statistic=float(stat),
        p_value=float(p),
        alpha=0.05,
        conclusion_ko=conclusion,
        detail_ko=detail,
        extra={"median_by_weekday": medians.to_dict()},
    )


def test_recent_vs_prior(
    daily_totals: pd.DataFrame, window_days: int = 14
) -> HypothesisTestResult:
    """
    Mann–Whitney U: last `window_days` vs the preceding `window_days` (non-overlapping).
    """
    d = daily_totals.sort_values("날짜").reset_index(drop=True)
    n = len(d)
    if n < 2 * window_days:
        return HypothesisTestResult(
            title="최근 구간 vs 직전 구간",
            null_hypothesis="최근 구간과 직전 구간의 일별 총매출 분포는 같다.",
            method="Mann–Whitney U",
            statistic=None,
            p_value=None,
            alpha=0.05,
            conclusion_ko="비교할 만큼의 일수가 부족합니다.",
            detail_ko=f"최소 {2 * window_days}일 이상의 일별 데이터가 필요합니다.",
        )
    prior = d.iloc[-2 * window_days : -window_days]["매출"].values
    recent = d.iloc[-window_days:]["매출"].values
    stat, p = stats.mannwhitneyu(recent, prior, alternative="two-sided")
    reject = p < 0.05
    r_med = float(np.median(recent))
    p_med = float(np.median(prior))
    direction = "최근 구간이 더 높은 경향" if r_med > p_med else "최근 구간이 더 낮은 경향"
    conclusion = (
        f"최근 {window_days}일과 직전 {window_days}일의 일별 총매출 분포 차이가 "
        f"5% 유의수준에서 통계적으로 유의합니다. ({direction})"
        if reject
        else f"최근 {window_days}일과 직전 {window_days}일의 차이는 5% 유의수준에서 "
        "통계적으로 유의하다고 보기 어렵습니다."
    )
    detail = (
        f"p-value = {_fmt_p(p)}. "
        f"최근 {window_days}일 중앙값 {r_med:,.0f}원 vs 직전 {window_days}일 중앙값 {p_med:,.0f}원."
    )
    return HypothesisTestResult(
        title="최근 구간 vs 직전 구간",
        null_hypothesis="최근 구간과 직전 구간의 일별 총매출 분포는 같다.",
        method="Mann–Whitney U (양측)",
        statistic=float(stat),
        p_value=float(p),
        alpha=0.05,
        conclusion_ko=conclusion,
        detail_ko=detail,
        extra={"recent_median": r_med, "prior_median": p_med},
    )


def test_monotonic_trend(daily_totals: pd.DataFrame) -> HypothesisTestResult:
    """Spearman rank correlation: time vs daily total (monotonic trend)."""
    d = daily_totals.sort_values("날짜").reset_index(drop=True)
    if len(d) < 5:
        return HypothesisTestResult(
            title="일별 총매출 추세",
            null_hypothesis="시간과 일별 총매출 사이에 단조 관계가 없다.",
            method="Spearman 상관",
            statistic=None,
            p_value=None,
            alpha=0.05,
            conclusion_ko="추세 검정을 하기엔 일수가 너무 적습니다.",
            detail_ko="최소 5일 이상 권장합니다.",
        )
    x = np.arange(len(d), dtype=float)
    rho, p = stats.spearmanr(x, d["매출"].values)
    reject = p < 0.05
    direction = "상승 추세" if rho and rho > 0 else "하락 추세" if rho and rho < 0 else "추세 불명확"
    conclusion = (
        f"전체 기간에서 일별 총매출에 통계적으로 유의한 단조 {direction}가 관찰됩니다."
        if reject and rho is not None
        else "전체 기간에 걸친 단조 추세는 5% 유의수준에서 강하게 말하기 어렵습니다."
    )
    detail = f"p-value = {_fmt_p(p)}. Spearman ρ = {rho:.3f} (단조 상관)."
    return HypothesisTestResult(
        title="일별 총매출 추세",
        null_hypothesis="시간과 일별 총매출 사이에 단조 관계가 없다.",
        method="Spearman rank correlation",
        statistic=float(rho) if rho is not None and not np.isnan(rho) else None,
        p_value=float(p) if p is not None and not np.isnan(p) else None,
        alpha=0.05,
        conclusion_ko=conclusion,
        detail_ko=detail,
        extra={"rho": rho},
    )


def test_category_line_amounts(df: pd.DataFrame) -> HypothesisTestResult:
    """
    Kruskal–Wallis on line-item 매출 across 분류 (which categories drive bigger tickets).
    """
    sub = df.dropna(subset=["분류", "매출"])
    cats = sub["분류"].unique()
    if len(cats) < 2:
        return HypothesisTestResult(
            title="분류별 건당 매출(라인) 분포",
            null_hypothesis="분류에 관계없이 라인 매출 분포는 같다.",
            method="Kruskal–Wallis",
            statistic=None,
            p_value=None,
            alpha=0.05,
            conclusion_ko="분류가 2개 미만이라 비교할 수 없습니다.",
            detail_ko="",
        )
    groups = [g["매출"].values for _, g in sub.groupby("분류", observed=True)]
    groups = [g for g in groups if len(g) >= 2]
    if len(groups) < 2:
        return HypothesisTestResult(
            title="분류별 건당 매출(라인) 분포",
            null_hypothesis="분류에 관계없이 라인 매출 분포는 같다.",
            method="Kruskal–Wallis",
            statistic=None,
            p_value=None,
            alpha=0.05,
            conclusion_ko="일부 분류의 표본이 너무 적습니다.",
            detail_ko="",
        )
    stat, p = stats.kruskal(*groups)
    reject = p < 0.05
    med = sub.groupby("분류", observed=True)["매출"].median().sort_values(ascending=False)
    conclusion = (
        "분류에 따라 라인 매출(건 단위) 분포가 통계적으로 다릅니다."
        if reject
        else "분류 간 라인 매출 분포 차이는 5% 유의수준에서 뚜렷하다고 보기 어렵습니다."
    )
    detail = f"p-value = {_fmt_p(p)}. 분류별 중앙값 상위: {', '.join(med.head(3).index.astype(str))}."
    return HypothesisTestResult(
        title="분류별 건당 매출(라인) 분포",
        null_hypothesis="분류에 관계없이 라인 매출 분포는 같다.",
        method="Kruskal–Wallis",
        statistic=float(stat),
        p_value=float(p),
        alpha=0.05,
        conclusion_ko=conclusion,
        detail_ko=detail,
        extra={"median_by_category": med.head(10).to_dict()},
    )


def run_default_battery(
    df: pd.DataFrame, daily_totals: pd.DataFrame, window_days: int = 14
) -> list[HypothesisTestResult]:
    """Standard set of tests for CEO-facing deck."""
    return [
        test_monotonic_trend(daily_totals),
        test_recent_vs_prior(daily_totals, window_days=window_days),
        test_weekday_effect(daily_totals),
        test_category_line_amounts(df),
    ]
