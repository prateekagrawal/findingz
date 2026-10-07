"""Course-controlled edits to an actual MadGraph run card."""
from __future__ import annotations

import math
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

RunCardValue = bool | int | float | str
# These already have dedicated controls and affect sample metadata or resource limits.
MANAGED_FIELDS = {"nevents", "iseed", "ebeam1", "ebeam2", "lpp1", "lpp2"}


def validate_name(name: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError(f"Invalid run-card parameter: {name!r}; use lowercase names")
    if name in MANAGED_FIELDS:
        raise ValueError(f"{name} is managed by the event, seed, or collider controls")


def format_value(value: RunCardValue) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("Run-card values must be finite")
        return str(value)
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.+/\-]+", value):
        if value.lower() in {"nan", "inf", "+inf", "-inf", "infinity"}:
            raise ValueError("Run-card values must be finite")
        return value
    raise ValueError("Use a number, boolean, or single text token for a run-card value")


def validate_overrides(values: dict[str, RunCardValue]) -> dict[str, RunCardValue]:
    for name, value in values.items():
        validate_name(name)
        format_value(value)
    return values


class RunCardOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    defaults: dict[str, RunCardValue] = Field(default_factory=dict)
    editable: list[str] = Field(default_factory=list)
    descriptions: dict[str, str] = Field(default_factory=dict)
    choices: dict[str, dict[str, str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_options(self):
        validate_overrides(self.defaults)
        for name in self.editable:
            validate_name(name)
        if len(set(self.editable)) != len(self.editable):
            raise ValueError("editable run-card names must be unique")
        return self


def parse_edits(text: str, options: RunCardOptions) -> dict[str, RunCardValue]:
    """Parse the native value = name convention, overlaid on course defaults."""
    result = dict(options.defaults)
    seen = set()
    for number, line in enumerate(text.splitlines(), 1):
        line = re.split(r"[!#]", line, maxsplit=1)[0].strip()
        if not line:
            continue
        fields = line.split("=")
        if len(fields) != 2:
            raise ValueError(f"Line {number}: use value = parameter")
        raw, name = (field.strip() for field in fields)
        if name not in options.editable:
            raise ValueError(f"Line {number}: {name!r} is not editable for this process")
        if name in seen:
            raise ValueError(f"Line {number}: duplicate parameter {name}")
        seen.add(name)
        value: RunCardValue
        if raw.lower() in {"true", ".true.", "false", ".false."}:
            value = raw.lower() in {"true", ".true."}
        elif re.fullmatch(r"[+-]?\d+", raw):
            value = int(raw)
        else:
            try:
                value = float(re.sub(r"[dD]", "e", raw))
            except ValueError:
                value = raw
        format_value(value)
        result[name] = value
    return validate_overrides(result)


def apply_overrides(card: str, values: dict[str, RunCardValue]) -> str:
    """Replace existing active entries only; never modify the parameter card."""
    validate_overrides(values)
    if not values:
        return card
    seen = set()
    output = []
    for line in card.splitlines(keepends=True):
        active = re.split(r"[!#]", line, maxsplit=1)[0]
        fields = active.split("=")
        name = fields[1].strip().lower() if len(fields) == 2 else None
        if name in values:
            if name in seen:
                raise ValueError(f"Duplicate entry {name} in generated run card")
            seen.add(name)
            # Keep the original name, comments and line ending.
            line = f"  {format_value(values[name])} =" + line.split("=", 1)[1]
        output.append(line)
    missing = set(values) - seen
    if missing:
        raise ValueError("Parameters absent from this process's run card: " + ", ".join(sorted(missing)))
    return "".join(output)
