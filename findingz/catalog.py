from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class Availability(BaseModel):
    enabled: bool = True
    available_from: date | None = None
    available_until: date | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> Availability:
        if (
            self.available_from is not None
            and self.available_until is not None
            and self.available_from > self.available_until
        ):
            raise ValueError("available_from must not be later than available_until")
        return self

    def is_available(self, on_date: date | None = None) -> bool:
        current = on_date or datetime.now().astimezone().date()
        return (
            self.enabled
            and (self.available_from is None or current >= self.available_from)
            and (self.available_until is None or current <= self.available_until)
        )


class DatasetEntry(Availability):
    label: str = Field(min_length=1, max_length=100)
    path: str = Field(min_length=1)
    provenance: str = Field(min_length=1, max_length=500)


class ModelEntry(Availability):
    label: str = Field(min_length=1, max_length=100)
    madgraph_name: str = Field(pattern=r"^[A-Za-z0-9_+-]+$")


class DetectorEntry(Availability):
    label: str = Field(min_length=1, max_length=100)
    card: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=500)


class ColliderEntry(Availability):
    label: str = Field(min_length=1, max_length=100)
    beam_type: Literal["pp", "ee"]
    beam_energy_gev: float = Field(ge=10.0, le=50_000.0)
    full_pipeline: bool = False
    detector_ids: list[str] = Field(default_factory=list)
    default_detector_id: str | None = None
    mass_window_gev: tuple[float, float]

    @model_validator(mode="after")
    def validate_mass_window(self) -> ColliderEntry:
        if self.mass_window_gev[0] >= self.mass_window_gev[1]:
            raise ValueError("collider mass_window_gev must be ordered")
        if self.default_detector_id is not None and self.default_detector_id not in self.detector_ids:
            raise ValueError("default_detector_id must be listed in detector_ids")
        if self.full_pipeline and self.default_detector_id is None:
            raise ValueError("full-pipeline colliders require a default_detector_id")
        return self


class ProcessEntry(Availability):
    label: str = Field(min_length=1, max_length=140)
    collider_ids: list[str] = Field(min_length=1)
    model_ids: list[str] = Field(min_length=1)
    madgraph_lines: list[str] = Field(min_length=1, max_length=8)
    minimum_com_energy_gev: float | None = Field(default=None, ge=0.0)
    full_pipeline: bool = False

    @model_validator(mode="after")
    def validate_commands(self) -> ProcessEntry:
        for index, line in enumerate(self.madgraph_lines):
            expected = "generate " if index == 0 else "add process "
            if not line.startswith(expected):
                raise ValueError(f"MadGraph line {index + 1} must start with {expected!r}")
            if any(token in line for token in ("\n", "\r", ";", "output ", "import ", "quit")):
                raise ValueError("MadGraph process lines may contain process definitions only")
        return self


class CourseFeatures(BaseModel):
    toy_generator: bool = False
    prepared_data_analysis: bool = True
    madgraph_only: bool = True
    full_pipeline: bool = True


class CourseCatalog(BaseModel):
    schema_version: Literal[1] = 1
    title: str = "Finding Z course catalogue"
    features: CourseFeatures = Field(default_factory=CourseFeatures)
    datasets: dict[str, DatasetEntry]
    models: dict[str, ModelEntry]
    detectors: dict[str, DetectorEntry]
    colliders: dict[str, ColliderEntry]
    processes: dict[str, ProcessEntry]

    @model_validator(mode="after")
    def validate_references(self) -> CourseCatalog:
        for collider_id, collider in self.colliders.items():
            missing_detectors = set(collider.detector_ids) - set(self.detectors)
            if missing_detectors:
                raise ValueError(
                    f"Collider {collider_id} references unknown detectors: "
                    f"{sorted(missing_detectors)}"
                )
        for process_id, process in self.processes.items():
            missing_colliders = set(process.collider_ids) - set(self.colliders)
            missing_models = set(process.model_ids) - set(self.models)
            if missing_colliders:
                raise ValueError(
                    f"Process {process_id} references unknown colliders: "
                    f"{sorted(missing_colliders)}"
                )
            if missing_models:
                raise ValueError(
                    f"Process {process_id} references unknown models: {sorted(missing_models)}"
                )
        return self

    def available_datasets(self, on_date: date | None = None) -> dict[str, DatasetEntry]:
        return {key: value for key, value in self.datasets.items() if value.is_available(on_date)}

    def available_models(self, on_date: date | None = None) -> dict[str, ModelEntry]:
        return {key: value for key, value in self.models.items() if value.is_available(on_date)}

    def available_detectors(self, on_date: date | None = None) -> dict[str, DetectorEntry]:
        return {key: value for key, value in self.detectors.items() if value.is_available(on_date)}

    def available_colliders(
        self, *, full_pipeline: bool = False, on_date: date | None = None
    ) -> dict[str, ColliderEntry]:
        return {
            key: value
            for key, value in self.colliders.items()
            if value.is_available(on_date) and (not full_pipeline or value.full_pipeline)
        }

    def available_processes(
        self,
        collider_id: str,
        model_id: str,
        *,
        full_pipeline: bool = False,
        on_date: date | None = None,
    ) -> dict[str, ProcessEntry]:
        collider = self.colliders[collider_id]
        center_of_mass_energy = 2.0 * collider.beam_energy_gev
        return {
            key: value
            for key, value in self.processes.items()
            if value.is_available(on_date)
            and collider_id in value.collider_ids
            and model_id in value.model_ids
            and (not full_pipeline or value.full_pipeline)
            and (
                value.minimum_com_energy_gev is None
                or center_of_mass_energy >= value.minimum_com_energy_gev
            )
        }


def default_catalog_path() -> Path:
    source = Path(__file__).resolve().parents[1] / "config" / "course_catalog.yaml"
    if source.exists():
        return source
    return Path(__file__).parent / "resources" / "config" / "course_catalog.yaml"


def catalog_path() -> Path:
    configured = os.environ.get("FINDINGZ_CATALOG_PATH")
    return Path(configured).expanduser().resolve() if configured else default_catalog_path()


def load_catalog(path: Path | None = None) -> CourseCatalog:
    source = (path or catalog_path()).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Course catalogue not found: {source}")
    payload = yaml.safe_load(source.read_text())
    if not isinstance(payload, dict):
        raise TypeError(f"Course catalogue must contain a YAML mapping: {source}")
    return CourseCatalog.model_validate(payload)


def resolve_catalog_path(relative_or_absolute: str, source: Path | None = None) -> Path:
    path = Path(relative_or_absolute)
    if path.is_absolute():
        return path
    return ((source or catalog_path()).parent / path).resolve()
