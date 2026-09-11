from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

ChannelName = Literal["ee", "mumu"]
ObservableName = Literal["mll", "ptll", "rapidity_ll", "cos_theta_cs"]
FilterVariable = Literal[
    "min_lepton_pt",
    "max_abs_lepton_eta",
    "mll",
    "ptll",
    "rapidity_ll",
    "cos_theta_cs",
]
FilterOperator = Literal[">", ">=", "<", "<=", "==", "between"]


class AnalysisFilter(BaseModel):
    variable: FilterVariable
    operator: FilterOperator
    value: float | list[float]

    @model_validator(mode="after")
    def validate_between(self) -> AnalysisFilter:
        if self.operator == "between":
            if not isinstance(self.value, list) or len(self.value) != 2:
                raise ValueError("A between filter requires exactly two values")
            if self.value[0] >= self.value[1]:
                raise ValueError("The lower bound must be smaller than the upper bound")
        elif isinstance(self.value, list):
            raise ValueError(f"Operator {self.operator} requires one numeric value")
        return self


class AnalysisPlan(BaseModel):
    """The only analysis request an LLM is allowed to send to the tool layer."""

    execute: bool = True
    clarification: str | None = None
    samples: list[str] = Field(
        default_factory=lambda: ["collision"],
        min_length=1,
        max_length=12,
    )
    channels: list[ChannelName] = Field(default_factory=list)
    filters: list[AnalysisFilter] = Field(default_factory=list)
    observable: ObservableName = "mll"
    plot: Literal["histogram", "overlay", "none"] = "histogram"
    explanation_topics: list[str] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def validate_execution_state(self) -> AnalysisPlan:
        if not self.execute and not self.clarification:
            raise ValueError("A non-executable plan must explain or request clarification")
        if self.execute and self.clarification:
            raise ValueError("An executable plan cannot also request clarification")
        if self.execute and not self.samples:
            raise ValueError("An executable plan needs at least one sample")
        return self


class ToolCallRecord(BaseModel):
    name: str
    arguments: dict[str, object]
    summary: str


class AnalysisSummary(BaseModel):
    observable: ObservableName
    selected_events: dict[str, int]
    means: dict[str, float]
    z_window_counts: dict[str, int]
    tool_calls: list[ToolCallRecord]
    data_provenance: str
