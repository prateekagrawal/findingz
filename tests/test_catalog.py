from datetime import date

import pytest
from pydantic import ValidationError

from findingz.catalog import CourseCatalog, load_catalog, resolve_catalog_path


def test_default_catalog_exposes_only_released_entries() -> None:
    catalog = load_catalog()
    assert not catalog.features.toy_generator
    assert catalog.features.madgraph_only
    assert set(catalog.available_datasets()) == {"signal", "background", "collision"}
    assert "sm" in catalog.available_models()
    assert "loop_sm" not in catalog.available_models()
    assert "blackbox_1" not in catalog.available_models()
    assert set(catalog.available_detectors()) == {"cms", "aleph", "idea"}
    assert set(catalog.available_colliders(full_pipeline=True)) == {
        "lhc13",
        "lep91",
        "higgs240",
    }
    assert catalog.colliders["lhc13"].default_detector_id == "cms"
    assert set(catalog.colliders["lhc13"].detector_ids) == {"cms"}
    assert "ee_zh_mumu" not in catalog.available_processes("lep91", "sm")
    assert "ee_zh_mumu" in catalog.available_processes("higgs240", "sm")
    assert "ee_mumu" in catalog.available_processes("lep91", "sm", full_pipeline=True)
    assert "ee_zh_mumu" in catalog.available_processes(
        "higgs240", "sm", full_pipeline=True
    )
    assert resolve_catalog_path(catalog.datasets["signal"].path).exists()


def test_catalog_release_dates_can_hide_an_entry() -> None:
    catalog = load_catalog()
    entry = catalog.models["sm"].model_copy(update={"available_from": date(2030, 1, 1)})
    assert not entry.is_available(date(2029, 12, 31))
    assert entry.is_available(date(2030, 1, 1))


def test_catalog_rejects_non_process_madgraph_commands() -> None:
    payload = load_catalog().model_dump(mode="json")
    payload["processes"]["dy_ll"]["madgraph_lines"] = ["output /tmp/unsafe"]
    with pytest.raises(ValidationError, match="must start with"):
        CourseCatalog.model_validate(payload)


def test_catalog_rejects_unknown_collider_detector() -> None:
    payload = load_catalog().model_dump(mode="json")
    payload["colliders"]["lhc13"]["detector_ids"] = ["not-installed"]
    payload["colliders"]["lhc13"]["default_detector_id"] = "not-installed"
    with pytest.raises(ValidationError, match="unknown detectors"):
        CourseCatalog.model_validate(payload)
