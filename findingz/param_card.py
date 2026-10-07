"""Numeric SLHA parameter edits identified by block and indices."""
from __future__ import annotations

import math
import re

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator

ParamCardValue = StrictInt | StrictFloat


def validate_parameter(name: str, value: ParamCardValue | None = None) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]*(?: -?\d+)*", name):
        raise ValueError(f"Use a lowercase SLHA block and indices, e.g. 'mass 23': {name!r}")
    parts = name.split()
    if parts[0] == "decay" and (len(parts) != 2 or int(parts[1]) == 0):
        raise ValueError("A decay entry must be 'decay PDG_ID'")
    if parts[0] in {"block", "qnumbers"}:
        raise ValueError("Block declarations and particle definitions are not parameter values")
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Parameter-card values must be finite numbers")
        if parts[0] == "decay" and value < 0:
            raise ValueError("Decay widths must be nonnegative")


def validate_overrides(values: dict[str, ParamCardValue]) -> dict[str, ParamCardValue]:
    for name, value in values.items():
        validate_parameter(name, value)
    return values


class ParamCardOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    defaults: dict[str, ParamCardValue] = Field(default_factory=dict)
    editable: list[str] = Field(default_factory=list)
    descriptions: dict[str, str] = Field(default_factory=dict)
    choices: dict[str, dict[str, str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_options(self):
        validate_overrides(self.defaults)
        for name in self.editable:
            validate_parameter(name)
        if len(set(self.editable)) != len(self.editable):
            raise ValueError("editable parameter-card names must be unique")
        return self


def parse_edits(text: str, options: ParamCardOptions) -> dict[str, ParamCardValue]:
    result = dict(options.defaults)
    seen = set()
    for number, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split("=")
        if len(fields) != 2:
            raise ValueError(f"Line {number}: use value = block indices, e.g. 91.2 = mass 23")
        raw, name = (field.strip() for field in fields)
        if name not in options.editable:
            raise ValueError(f"Line {number}: {name!r} is not editable for this model/process")
        if name in seen:
            raise ValueError(f"Line {number}: duplicate parameter {name}")
        seen.add(name)
        try:
            value = float(re.sub(r"[dD]", "e", raw))
        except ValueError:
            raise ValueError(f"Line {number}: parameter-card values must be numbers") from None
        validate_parameter(name, value)
        result[name] = value
    return validate_overrides(result)


def apply_overrides(card: str, values: dict[str, ParamCardValue]) -> str:
    validate_overrides(values)
    if not values:
        return card
    block = None
    dependent = False
    seen = set()
    output = []
    for line in card.splitlines(keepends=True):
        if "dependent parameters" in line.lower() and line.lstrip().startswith("#"):
            dependent = True
        active, _, comment = line.partition("#")
        tokens = active.split()
        key = None
        if tokens and tokens[0].lower() == "block":
            block = tokens[1].lower() if len(tokens) >= 2 else None
            dependent = False
        elif tokens and tokens[0].lower() == "decay":
            block = None  # Branching ratios are not block entries.
            if len(tokens) >= 3:
                key = f"decay {tokens[1]}"
        elif block and tokens:
            key = " ".join([block, *tokens[:-1]])
        if key in values:
            if dependent:
                raise ValueError(f"{key} is marked dependent by this model; edit its independent inputs instead")
            if key in seen:
                raise ValueError(f"Ambiguous repeated SLHA entry: {key}")
            seen.add(key)
            tokens[-1] = str(values[key])
            ending = "\n" if line.endswith("\n") else ""
            line = "  " + "  ".join(tokens) + (" #" + comment.rstrip("\r\n") if "#" in line else "") + ending
        output.append(line)
    missing = set(values) - seen
    if missing:
        raise ValueError("Parameters absent from this model's parameter card: " + ", ".join(sorted(missing)))
    return "".join(output)
