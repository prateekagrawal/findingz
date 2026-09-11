from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from .data import describe_sample, load_sample
from .physics import add_observables
from .schemas import AnalysisFilter, AnalysisPlan, AnalysisSummary, ToolCallRecord


@dataclass
class ExecutionResult:
    summary: AnalysisSummary
    selected: dict[str, pd.DataFrame]
    figure: Figure | None


def _apply_filter(frame: pd.DataFrame, item: AnalysisFilter) -> pd.DataFrame:
    series = frame[item.variable]
    if item.operator == ">":
        mask = series > float(item.value)
    elif item.operator == ">=":
        mask = series >= float(item.value)
    elif item.operator == "<":
        mask = series < float(item.value)
    elif item.operator == "<=":
        mask = series <= float(item.value)
    elif item.operator == "==":
        mask = series == float(item.value)
    else:
        lower, upper = item.value
        mask = series.between(lower, upper, inclusive="both")
    return frame.loc[mask].copy()


def _make_figure(selected: dict[str, pd.DataFrame], plan: AnalysisPlan) -> Figure | None:
    if plan.plot == "none":
        return None
    figure = Figure(figsize=(8, 5))
    axis = figure.subplots()
    colors = {"signal": "#d95f02", "background": "#1b9e77", "collision": "#202020"}
    fallback_colors = ["#7570b3", "#e7298a", "#66a61e", "#e6ab02"]
    observable = plan.observable
    finite_values = [
        frame[observable].to_numpy(dtype=float)
        for frame in selected.values()
        if len(frame) and np.isfinite(frame[observable]).any()
    ]
    if finite_values:
        combined = np.concatenate(finite_values)
        low, high = float(np.nanmin(combined)), float(np.nanmax(combined))
        if observable == "mll":
            low, high = max(0.0, low - 2.0), high + 2.0
        bins = np.linspace(low, high if high > low else low + 1.0, 31)
        for sample_index, (sample, frame) in enumerate(selected.items()):
            groups = [(sample, frame)]
            if len(plan.channels) > 1:
                groups = [
                    (f"{sample}:{channel}", frame.loc[frame["channel"].eq(channel)])
                    for channel in plan.channels
                ]
            for label, group in groups:
                axis.hist(
                    group[observable],
                    bins=bins,
                    histtype="step" if sample != "collision" else "stepfilled",
                    alpha=0.25 if sample == "collision" else 0.9,
                    linewidth=2,
                    weights=group.get("weight"),
                    color=colors.get(sample, fallback_colors[sample_index % len(fallback_colors)]),
                    linestyle="--" if label.endswith(":mumu") else "-",
                    label=label,
                )
    unit = " [GeV]" if observable in {"mll", "ptll"} else ""
    axis.set_xlabel(f"{observable}{unit}")
    axis.set_ylabel("Weighted events")
    axis.set_title("Finding Z prepared dilepton sample")
    axis.legend()
    axis.grid(alpha=0.2)
    figure.tight_layout()
    return figure


def execute_plan(plan: AnalysisPlan, data_dir: Path | None = None) -> ExecutionResult:
    if not plan.execute:
        raise ValueError("A clarification plan cannot be executed")

    calls: list[ToolCallRecord] = []
    selected: dict[str, pd.DataFrame] = {}
    provenance: list[str] = []
    for sample in plan.samples:
        description = describe_sample(sample, data_dir)
        provenance.append(f"{sample}: {description['source']}")
        calls.append(
            ToolCallRecord(
                name="describe_dataset",
                arguments={"sample": sample},
                summary=f"{description['events']} events; channels {description['channels']}",
            )
        )
        frame = add_observables(load_sample(sample, data_dir))
        calls.append(
            ToolCallRecord(
                name="reconstruct_observable",
                arguments={"sample": sample, "observable": plan.observable},
                summary=f"Computed {plan.observable} from measured lepton four-vectors",
            )
        )
        if plan.channels:
            frame = frame.loc[frame["channel"].isin(plan.channels)].copy()
        for item in plan.filters:
            frame = _apply_filter(frame, item)
        selected[sample] = frame
        calls.append(
            ToolCallRecord(
                name="select_events",
                arguments={
                    "sample": sample,
                    "channels": list(plan.channels),
                    "filters": [item.model_dump() for item in plan.filters],
                },
                summary=f"Selected {len(frame)} events",
            )
        )

    figure = _make_figure(selected, plan)
    if figure is not None:
        calls.append(
            ToolCallRecord(
                name="make_plot",
                arguments={"observable": plan.observable, "kind": plan.plot},
                summary="Created a weighted comparison histogram",
            )
        )

    counts = {sample: len(frame) for sample, frame in selected.items()}
    means = {
        sample: float(frame[plan.observable].mean()) if len(frame) else float("nan")
        for sample, frame in selected.items()
    }
    window_counts = {
        sample: int(frame["mll"].between(80.0, 100.0).sum()) for sample, frame in selected.items()
    }
    calls.append(
        ToolCallRecord(
            name="summarize_selection",
            arguments={"z_mass_window_GeV": [80.0, 100.0]},
            summary=f"Counts in the 80-100 GeV Z window: {window_counts}",
        )
    )
    summary = AnalysisSummary(
        observable=plan.observable,
        selected_events=counts,
        means=means,
        z_window_counts=window_counts,
        tool_calls=calls,
        data_provenance="; ".join(provenance),
    )
    return ExecutionResult(summary=summary, selected=selected, figure=figure)
