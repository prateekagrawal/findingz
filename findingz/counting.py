from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import NormalDist

import pandas as pd


@dataclass(frozen=True)
class CutAndCountResult:
    """Small, explicit set of single-bin counting-experiment summaries."""

    signal_yield: float
    background_yield: float
    observed_count: int | None
    signal_to_background: float
    signal_over_sqrt_background: float
    asimov_significance: float
    approximate_significance_with_systematic: float
    approximate_expected_upper_limit_events: float
    approximate_expected_signal_strength_limit: float
    background_uncertainty_fraction: float
    background_only_p_value: float | None
    observed_significance: float | None

    def as_dict(self) -> dict[str, float | int | None]:
        return asdict(self)


def weighted_yield(frame: pd.DataFrame) -> float:
    """Return the sum of event weights, or the row count when no weights exist."""
    if "weight" not in frame:
        return float(len(frame))
    weights = pd.to_numeric(frame["weight"], errors="raise")
    if not weights.map(math.isfinite).all() or (weights < 0.0).any():
        raise ValueError("Cut-and-count weights must be finite and non-negative")
    return float(weights.sum())


def asimov_significance(signal: float, background: float) -> float:
    """Median expected discovery significance for a known background."""
    if signal < 0.0 or background < 0.0:
        raise ValueError("Expected signal and background yields must be non-negative")
    if signal == 0.0:
        return 0.0
    if background == 0.0:
        return float("inf")
    return math.sqrt(2.0 * ((signal + background) * math.log1p(signal / background) - signal))


def poisson_survival(observed: int, expected: float) -> float:
    """P(N >= observed | expected) for an integer Poisson count."""
    if observed < 0 or expected < 0.0:
        raise ValueError("Poisson inputs must be non-negative")
    if observed == 0:
        return 1.0
    if expected == 0.0:
        return 0.0

    # Summing the smaller side avoids both long tails and catastrophic cancellation.
    if observed <= expected:
        log_expected = math.log(expected)
        cdf = math.fsum(
            math.exp(-expected + count * log_expected - math.lgamma(count + 1.0))
            for count in range(observed)
        )
        return min(1.0, max(0.0, 1.0 - cdf))

    log_term = -expected + observed * math.log(expected) - math.lgamma(observed + 1.0)
    term = math.exp(log_term)
    survival = term
    count = observed
    while term > max(survival, 1.0) * 1e-15:
        count += 1
        term *= expected / count
        survival += term
    return min(1.0, max(0.0, survival))


def _one_sided_gaussian_significance(p_value: float) -> float:
    if p_value >= 0.5:
        return 0.0
    if p_value <= 0.0:
        return float("inf")
    if p_value >= 1e-15:
        return float(NormalDist().inv_cdf(1.0 - p_value))

    # Acklam's lower-tail rational approximation avoids cancellation in 1 - p.
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838,
        -2.549732539343734,
        4.374664141464968,
        2.938163982698783,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996,
        3.754408661907416,
    )
    q = math.sqrt(-2.0 * math.log(p_value))
    numerator = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
    denominator = ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    return -numerator / denominator


def summarize_cut_and_count(
    signal: pd.DataFrame,
    background: pd.DataFrame,
    observed: pd.DataFrame | None = None,
    *,
    background_uncertainty_fraction: float = 0.0,
) -> CutAndCountResult:
    """Summarize one selected signal region using teaching-level approximations."""
    if not 0.0 <= background_uncertainty_fraction <= 1.0:
        raise ValueError("Background uncertainty fraction must lie between zero and one")

    signal_yield = weighted_yield(signal)
    background_yield = weighted_yield(background)
    observed_count = len(observed) if observed is not None else None
    signal_to_background = (
        signal_yield / background_yield if background_yield else float("inf")
    )
    signal_over_sqrt_background = (
        signal_yield / math.sqrt(background_yield)
        if background_yield
        else (float("inf") if signal_yield else 0.0)
    )
    systematic_variance = (
        background_uncertainty_fraction * background_yield
    ) ** 2
    denominator = math.sqrt(background_yield + systematic_variance)
    approximate_with_systematic = (
        signal_yield / denominator
        if denominator
        else (float("inf") if signal_yield else 0.0)
    )
    # One-sided Gaussian 95% approximation. The three-event floor prevents the
    # zero-background limit from becoming spuriously zero in this teaching estimate.
    approximate_limit_events = max(3.0, 1.6448536269514722 * denominator)
    approximate_signal_strength_limit = (
        approximate_limit_events / signal_yield if signal_yield else float("inf")
    )

    p_value = (
        poisson_survival(observed_count, background_yield)
        if observed_count is not None
        else None
    )
    observed_significance = (
        _one_sided_gaussian_significance(p_value) if p_value is not None else None
    )
    return CutAndCountResult(
        signal_yield=signal_yield,
        background_yield=background_yield,
        observed_count=observed_count,
        signal_to_background=signal_to_background,
        signal_over_sqrt_background=signal_over_sqrt_background,
        asimov_significance=asimov_significance(signal_yield, background_yield),
        approximate_significance_with_systematic=approximate_with_systematic,
        approximate_expected_upper_limit_events=approximate_limit_events,
        approximate_expected_signal_strength_limit=approximate_signal_strength_limit,
        background_uncertainty_fraction=background_uncertainty_fraction,
        background_only_p_value=p_value,
        observed_significance=observed_significance,
    )
