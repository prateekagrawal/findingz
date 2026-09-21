# CIT changes to collect after testing

Working handoff list, started 2026-09-15. Do not send yet: Prateek will request
one consolidated message after testing. These are requests, not confirmed image changes.

## Requested image / environment changes

- [ ] Update the existing FindingZ installation in `hep` to the agreed commit.
  Record that commit; test exported notebooks before distributing course updates.
- [ ] Point both the app and notebook environment at the same nbgitpuller checkout
  for `FINDINGZ_CATALOG_PATH`, `FINDINGZ_VARIABLES_PATH`, and
  `FINDINGZ_NOTEBOOK_TEMPLATE`. Keep persistent run storage separate; set
  `FINDINGZ_NOTEBOOK_DIR=/home/jovyan/work` for new work. Preserve any existing
  notebooks in older directories rather than moving or overwriting them.

- [x] Prateek confirmed (2026-09-21) that `awkward` and `uproot` are available
  in `hep`. No additional installation request is needed.
- [ ] Make `hep` the default Python environment for student work, including
  terminals and, importantly, newly opened/created notebooks. Register a visible
  **Python (hep)** kernel in the image and configure Jupyter to select it by
  default. Terminal activation alone does not select the notebook kernel.
  JupyterHub's server process may remain in its existing base environment.
- [ ] Set `FINDINGZ_NOTEBOOK_KERNEL=hep` for FindingZ exports.
- [ ] Persist `delphes_path = /opt/conda/envs/hep/bin/` in MadGraph's
  `mg5_configuration.txt` in the image. Prateek tested this path successfully
  and obtained `tag_1_delphes_events.root`.

## Acceptance checks

In a fresh student session, without manual kernel registration or package installs:

```python
import sys
print(sys.executable)  # /opt/conda/envs/hep/bin/python
import findingz.notebook_analysis
import awkward
import uproot
```

Check both a newly created notebook and a FindingZ-exported notebook: saved
kernel metadata can affect which kernel is selected. In a new terminal,
`command -v python` should also select the hep interpreter.

## Testing evidence

- The notebook initially ran `/opt/conda/bin/python` and could not import FindingZ.
- Registering the hep kernel and restarting the server exposed **Python (hep)**;
  selecting it made the FindingZ import work.
- The earlier missing-package report was superseded by confirmation that Awkward
  and Uproot are available in hep; retain the fresh-session import check.
- Local native Jupyter execution, including browser Run All Cells, was verified
  on 2026-09-21. This is not verification of the updated CIT image. The separate
  native notebook Docker image is a local Apple Silicon solution, not a CIT request.

## Separate application follow-up (not a CIT installation request)

- Install FindingZ >= 0.2.0 before publishing course catalogues with `ufo_path`
  or `dataset_folders`. These use instructor-supplied filesystem directories;
  no base HEP-stack change is required for compatible UFOs. See
  `deploy/EXTERNAL-COURSE-CONTENT.md`. Preserve course/shared mounts and student
  run directories. Test the app update before distributing new model content.

- Local UI update (2026-09-20): no automatically selected plotting/counting samples;
  updated 2026-09-21 to one null-versus-complete-alternative comparison. Displays
  both counts and their signed difference, with a rough signed expected separation;
  never adds the predictions. Zero default null uncertainty; no limit-setting UI.
  Include the new compare_samples notebook helper before releasing dependent course
  templates. Old saved additive notebooks retain their original API semantics.

- Keep CSV-only notebook analysis independent of optional ROOT/object-reading
  dependencies where feasible. Track this separately from installing dependencies
  needed for the object-level exercises.
