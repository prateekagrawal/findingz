"""The local app and notebook server must consume the same external course files."""
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]


def test_both_services_share_external_course_and_student_storage():
    compose = yaml.safe_load((ROOT / "docker-compose.hep.yml").read_text())
    app = compose["services"]["findingz"]
    notebook = compose["services"]["jupyter"]
    for key in ("FINDINGZ_CATALOG_PATH", "FINDINGZ_VARIABLES_PATH",
                "FINDINGZ_NOTEBOOK_TEMPLATE", "FINDINGZ_NOTEBOOK_DIR",
                "FINDINGZ_RUN_ROOT"):
        assert app["environment"][key] == notebook["environment"][key]
    for service in (app, notebook):
        mount = next(v for v in service["volumes"] if isinstance(v, dict))
        assert mount["target"] == "/workspace/course-materials"
        assert mount["source"] == "${FINDINGZ_COURSE_ROOT:-../course-materials}"
        assert mount["bind"]["create_host_path"] is False
        assert "findingz-runs:/workspace/runs" in service["volumes"]
        assert "findingz-notebooks:/workspace/notebooks" in service["volumes"]
        for key in ("FINDINGZ_CATALOG_PATH", "FINDINGZ_VARIABLES_PATH",
                    "FINDINGZ_NOTEBOOK_TEMPLATE"):
            assert service["environment"][key].startswith(mount["target"] + "/")


def test_notebook_startup_does_not_seed_course_files_from_image():
    script = (ROOT / "scripts/start_jupyter.sh").read_text()
    assert "cp " not in script
    assert "/opt/findingz/notebooks" not in script
    assert "FINDINGZ_NOTEBOOK_DIR" in script
