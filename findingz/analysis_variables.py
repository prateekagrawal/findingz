"""Reloadable variable definitions shared by the plotting and counting interfaces."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .catalog import catalog_path
from .hypotheses import AnalysisSample


class AnalysisVariable(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    column: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    step: float = Field(gt=0)
    enabled: bool = True


class VariableCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    variables: dict[str, AnalysisVariable]
    default_variables: list[str]
    processes: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> VariableCatalog:
        for names in [self.default_variables, *self.processes.values()]:
            if len(names) != len(set(names)):
                raise ValueError("Variable lists must not contain duplicates")
            unknown = set(names) - self.variables.keys()
            if unknown:
                raise ValueError(f"Unknown analysis variables: {sorted(unknown)}")
        return self

    def available(
        self, samples: list[AnalysisSample], frames: dict[str, pd.DataFrame]
    ) -> dict[str, AnalysisVariable]:
        """Use common process variables without restricting which samples can be selected."""
        allowed = set(self.variables)
        for sample in samples:
            names = self.processes.get(str(sample.config.get("process", "")), self.default_variables)
            allowed.intersection_update(names)
        return {
            name: variable
            for name, variable in self.variables.items()
            if name in allowed and variable.enabled
            and all(variable.column in frame.columns for frame in frames.values())
        }


def variable_catalog_path() -> Path:
    configured = os.environ.get("FINDINGZ_VARIABLES_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return catalog_path().with_name("analysis_variables.yaml")


def load_variable_catalog(path: Path | None = None) -> VariableCatalog:
    # Deliberately uncached: edits take effect on the next Streamlit rerun.
    source = path or variable_catalog_path()
    return VariableCatalog.model_validate(yaml.safe_load(source.read_text()))


def slider_bounds(frames: list[pd.DataFrame], variable: AnalysisVariable) -> tuple[float, float]:
    values = pd.concat([frame[variable.column] for frame in frames], ignore_index=True)
    values = pd.to_numeric(values, errors="coerce")
    values = values[np.isfinite(values)]
    if values.empty:
        return 0.0, variable.step
    low = math.floor(float(values.min()) / variable.step) * variable.step
    high = math.ceil(float(values.max()) / variable.step) * variable.step
    if low == high:
        high = low + variable.step
    return low, high


def apply_windows(
    frame: pd.DataFrame,
    windows: dict[str, tuple[float, float]],
    variables: dict[str, AnalysisVariable],
) -> pd.DataFrame:
    selected = frame
    for name, bounds in windows.items():
        values = pd.to_numeric(selected[variables[name].column], errors="coerce")
        selected = selected.loc[values.between(*bounds)]
    return selected.copy()
