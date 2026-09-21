# Two repositories, one application

FindingZ code and Python helpers are installed in the image. Course files remain
external, and student runs/work remain in persistent storage outside both repos.
Local Docker and CIT follow this same separation, not identical toolchain paths
or versions. CIT provides Conda hep and JupyterHub; local Docker provides its own
Python/HEP stack and localhost JupyterLab. Do not replace CIT's toolchain with the
local Dockerfile just to match paths.

## Local testing

Keep sibling Git checkouts `findingz` and `course-materials`. From `findingz`:

```bash
docker compose -p findingz -f docker-compose.hep.yml --profile advanced config --quiet
docker compose -p findingz -f docker-compose.hep.yml --profile advanced up -d --build
```

Docker must be allowed to read the course checkout. `FINDINGZ_COURSE_ROOT` may
override the host path. Both services use the same external catalog, variables,
template, runs and writable notebook directory. Existing run/notebook volumes
are preserved; never use `down -v`. The old course-config volume is retained for
recovery but is no longer the active configuration.

Edit course files in the course Git checkout; changes are read on app rerun or
new notebook export. Edit application code only in the FindingZ checkout; rebuild
the installed package to test it. Existing saved notebooks do not update.

## Publishing tested changes

1. Test uncommitted work locally: unit tests, configuration loading, notebook
   export/execution, and relevant simulation checks. Record which checks passed;
   a healthy web server alone does not validate notebook execution or physics.
2. Commit each repository's changes separately and record both Git commit IDs.
   Push only tested changes intended for the deployed branch. Never use a course
   push as a way to update the installed FindingZ package.
3. For app/API changes, CIT builds and tests an image from the chosen app commit
   first. Only then publish dependent course templates to the branch students
   pull. Use a separate test branch while the matching image is unavailable.
4. For compatible course-only changes, no image rebuild is needed. Students
   follow the nbgitpuller link to sync; a GitHub push is not automatic delivery.
   nbgitpuller preserves student edits, so originals should be left untouched.
5. Verify the pair on CIT before freezing it for the quarter. Record app commit,
   course commit and CIT's image identifier in the handoff. Do not claim the
   local HEP image is binary-identical to CIT's.

## Current pending release

### FindingZ 0.2.0 candidate — 2026-09-21

Publish both repositories on the existing `codex/initial-layout` branch, as
requested by the instructor: no students are using this deployment yet. Keep
the existing nbgitpuller link unchanged. CIT must install and validate 0.2.0
before testing the updated course notebooks.
The candidate course catalogue requires 0.2.0 and its notebooks use
`compare_samples` / `comparison_table`. All 147 app tests pass; external UFO
import/process generation has been tested locally. These checks do not resolve
the historical live-notebook plotting blocker below or establish CIT acceptance.
Do not open this deployment to students until that acceptance check passes.

The packaged simplified template uses new `load_analysis` and `enable_inline_plots`
helpers, and course notebooks require the comparison helpers. Repository updates
do not update CIT's installed package. See `CIT-PENDING-CHANGES.md` for the
consolidated request. The older activation notes below are historical.

### Local activation check — 2026-09-15

- Docker folder access is now working; the two-repository Compose layout is active.
- FindingZ and JupyterLab both load the installed package from site-packages and
  read identical external catalog, variable-definition and template files.
- Existing persistent storage remains accessible: 5 run directories and 25 notebooks.
- All 122 unit/regression tests pass; both service health checks pass.
- Live kernel smoke test passes imports, cell state/output and sample discovery,
  but times out at the inline Matplotlib plot cell. Notebook plotting remains a
  local release blocker; this does not establish a corresponding failure on CIT.
- No new app/course changes have been pushed. Resolve the notebook check before
  publishing the pair; do not update the student nbgitpuller branch prematurely.
