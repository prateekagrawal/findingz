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

### Published course configuration restored — 2026-09-30

- The active course catalogue and analysis-variable configuration match the
  fetched course repository revision `1a22906696ba06ec27e301ddc3bdccc716957fed`.
  MARK II, LHC, LEP and Higgs-factory presets are available; advanced card
  editors remain hidden. This replaces the temporary MARK-II-only setting.
- The full local regression suite passes (one optional-dependency test skipped).
  The running web container successfully loads the restored catalogue and passes
  its health check. Earlier local simulation and notebook checks are recorded below.
- Before freezing 0.2.0, commit and record the app/course revisions and validate
  the matching image on CIT: a small MARK II run, reopening its saved sample,
  and execution of an exported notebook with a plot. CIT acceptance is pending.
- Raw MadGraph-directory importing and full-pipeline validation for the new beam
  examples remain outside this release's verified scope.

### Card customization added to the 0.2.0 candidate — 2026-09-30

- Catalogue schema 2 adds optional run/parameter defaults and editable entries,
  plus course-supplied and student-editable Pythia/Delphes cards. Existing schema-1
  catalogues remain supported. Existing saved samples remain readable; the new
  analysis schema changes identities for newly generated runs.
- New run identities and manifests record edits; effective native cards are
  retained. Collision setup, analysis level and normalization constrain counting;
  generation/shower/detector differences produce nonblocking warnings. Model
  parameter differences remain available for hypothesis comparisons.
- A local 100-event QED full-pipeline smoke run completed through MadGraph,
  Pythia and Delphes with all four card customizations: 10.23 pb and 80 selected
  reconstructed pairs. This is an integration check, not a physics benchmark or
  CIT acceptance test. The sample was discoverable through FindingZ's run loader.
- Local testing verified schema 2; the active course catalogue has since returned
  to schema 1 with advanced card editors hidden at the instructor's request.
  `config/card_customization.example.yaml` documents how to expose them later.
  Do not deploy schema-2 content to CIT ahead of this application build.
- Raw MadGraph directory import remains future work. Scripted runs through
  `run_hep_simulation` already produce FindingZ-compatible samples; examples and
  current analysis limitations are in `EXTERNAL-COURSE-CONTENT.md`.

Local activation on 2026-09-30: rebuilt and restarted both Compose services.
The browser loads all four card editors, both services are healthy, and all 8
saved runs and 61 notebooks remain in persistent storage. Both notebook kernels
(`findingz` and `python3`) passed real execution checks for imports, cell state,
sample loading, text output and inline Matplotlib plots. This is local validation;
the CIT image and kernel registration have not been verified by these checks.

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
