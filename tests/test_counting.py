import json
import math
from pathlib import Path

import pandas as pd
import pytest

from findingz.counting import (
    asimov_significance,
    poisson_survival,
    summarize_cut_and_count,
    weighted_yield,
)


def test_weighted_yield_uses_event_weights() -> None:
    frame = pd.DataFrame({"weight": [0.25, 0.5, 1.25]})
    assert weighted_yield(frame) == pytest.approx(2.0)


def test_cut_and_count_reports_expected_and_observed_statistics() -> None:
    signal = pd.DataFrame({"weight": [2.0] * 5})
    background = pd.DataFrame({"weight": [1.0] * 25})
    observed = pd.DataFrame(index=range(36))
    result = summarize_cut_and_count(
        signal,
        background,
        observed,
        background_uncertainty_fraction=0.2,
    )

    assert result.signal_yield == 10.0
    assert result.background_yield == 25.0
    assert result.observed_count == 36
    assert result.signal_to_background == pytest.approx(0.4)
    assert result.signal_over_sqrt_background == pytest.approx(2.0)
    assert 0.0 < result.asimov_significance < 2.0
    assert result.approximate_significance_with_systematic == pytest.approx(10 / math.sqrt(50))
    assert result.approximate_expected_upper_limit_events == pytest.approx(
        1.6448536269514722 * math.sqrt(50)
    )
    assert result.approximate_expected_signal_strength_limit == pytest.approx(
        result.approximate_expected_upper_limit_events / 10.0
    )
    assert result.background_only_p_value is not None
    assert 0.0 < result.background_only_p_value < 0.5
    assert result.observed_significance is not None
    assert result.observed_significance > 0.0


def test_poisson_survival_handles_boundaries() -> None:
    assert poisson_survival(0, 2.0) == 1.0
    assert poisson_survival(1, 0.0) == 0.0
    assert poisson_survival(1, 2.0) == pytest.approx(1.0 - math.exp(-2.0))
    assert asimov_significance(0.0, 5.0) == 0.0


def test_observed_significance_remains_finite_for_tiny_p_value() -> None:
    result = summarize_cut_and_count(
        pd.DataFrame({"weight": [1.0]}),
        pd.DataFrame({"weight": [1.0] * 50}),
        pd.DataFrame(index=range(200)),
    )
    assert result.background_only_p_value is not None
    assert result.background_only_p_value < 1e-30
    assert result.observed_significance is not None
    assert result.observed_significance > 10.0


def test_cut_and_count_rejects_invalid_weights_and_uncertainty() -> None:
    with pytest.raises(ValueError, match="weights"):
        weighted_yield(pd.DataFrame({"weight": [1.0, -0.5]}))
    with pytest.raises(ValueError, match="uncertainty"):
        summarize_cut_and_count(pd.DataFrame(), pd.DataFrame(), background_uncertainty_fraction=1.1)


def test_cut_and_count_notebook_uses_course_kernel_and_helpers() -> None:
    notebook = json.loads(Path("notebooks/04_cut_and_count.ipynb").read_text())
    source = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    )

    assert notebook["metadata"]["kernelspec"]["name"] == "findingz"
    assert "summarize_cut_and_count" in source
    assert "build_sample_library(load_catalog(), default_run_root())" in source
    assert "validate_analysis_context(hypotheses)" in source
    assert "validate_counting_samples(hypotheses)" in source
    assert "sample.expected_frame(integrated_luminosity_fb)" in source
