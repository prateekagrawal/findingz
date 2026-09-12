# Finding Z — one application, local and CIT deployments

This is the application repository layout. The matching `course-materials` tree
contains live course configuration and student notebooks. No upstream simulation
installations, production event data, Docker image archives or private student work belong
in this application repository. Local Docker build instructions remain available;
CIT should use its existing toolchain rather than build that Dockerfile.

## Install on CIT

Activate `hep`, then from this repository install the application:

```bash
conda activate hep
python -m pip install '.[hep]'
```

First have CIT review dependency resolution against its working Conda environment.
This installs Finding Z and its Python dependencies, not MadGraph/Pythia/Delphes.
Do not overwrite CIT's working kernelspecs using the local notebook-kernel installer.

Copy `deploy/cit.env.example` to a deployment-controlled location, set the actual
course checkout and persistent run directory, and source it before launch.
No fixed per-user Jupyter URL is required. The UI command is:

```bash
findingz-ui --server.address=127.0.0.1 --server.port=8501
```

CIT should connect its existing Streamlit launcher to this command in `hep`.
Finding Z listens on port 8501; CIT's ServerProxy handles authentication and routing.
If CIT's proxy requires a Streamlit URL prefix, set `--server.baseUrlPath` to match
that routing configuration. Do not infer a fixed user-specific URL or add
application authentication. The optional notebook link below does not configure
the server, proxy, or authentication.

## Local testing of the same application

Use this Git checkout as the only application source. From this directory:

The default local setup uses the packaged notebook template. For live course
template edits, clone course materials beside this checkout in `course-materials`
or set `FINDINGZ_COURSE_ROOT` to its absolute path, grant Docker Desktop access
to that folder, and add `-f deploy/compose.course-template.yml` after the primary
Compose file. That optional override mounts the template read-only; edits are
picked up on the next notebook creation without rebuilding. Existing student
notebooks are unchanged. CIT uses FINDINGZ_NOTEBOOK_TEMPLATE directly and does not
need this Docker Desktop override.

```bash
git pull --ff-only
docker compose -p findingz -f docker-compose.hep.yml --profile advanced up -d --build
```

The local image installs Finding Z as a regular Python package and launches
`findingz-ui`, just like CIT. Source is not live-mounted: rebuild after pulling
or editing code. Local changes must be committed and pushed before CIT can use
them. CIT's image rebuild must install the same revision to match the application.

Always retain the `-p findingz` project name so the existing named run/notebook
volumes are reused. Do not use `down -v` when updating.
Local URLs are http://localhost:8501/ and http://localhost:8889/.

This mirrors the installed-application structure, not CIT's JupyterHub deployment
or exact Conda toolchain. Local Docker supplies its own simulation tools and a
separate localhost-only JupyterLab service; CIT supplies its existing tools and
authenticated JupyterLab/ServerProxy. Course configuration and student runs stay
outside the installed Python package on both.

## Portable settings and cards

- FINDINGZ_CATALOG_PATH: live course catalog (dropdowns, availability, samples).
- FINDINGZ_VARIABLES_PATH: live observable definitions; by default next to catalog.
- FINDINGZ_RUN_ROOT: persistent writable student run storage.
- FINDINGZ_NOTEBOOK_DIR: persistent writable directory for new student notebooks;
  defaults to ~/findingz-notebooks. Displayed below the basic analysis.
- FINDINGZ_NOTEBOOK_TEMPLATE: editable nbformat-4 course template; use
  notebooks/templates/analysis_template.ipynb from the course checkout.
  Omit to use the packaged fallback. Exactly one code cell must have the metadata
  tag findingz-settings; Finding Z replaces only that cell and clears outputs.
- FINDINGZ_NOTEBOOK_URL_PREFIX: optional JupyterLab lab/tree/ URL prefix mapping
  exactly to FINDINGZ_NOTEBOOK_DIR. The app appends the new filename. Leave unset
  on CIT unless its routing is configured; saving still works and the file path
  is shown. This replaces the old fixed FINDINGZ_JUPYTER_URL setting.
  Each notebook action only saves the file. With a prefix configured, a normal
  "Open saved notebook in JupyterLab" link appears after saving. There is no
  automatic navigation or custom browser component.
  Without a prefix, the controls explicitly save only and show the file path.
- FINDINGZ_MG5, FINDINGZ_PYTHIA8_DIR, FINDINGZ_DELPHES_DIR: installed tool locations.
- FINDINGZ_CARD_ROOT: optional independent root for catalog-relative detector cards.
- FINDINGZ_HEP_IMAGE_ID: optional, manually assigned simulation-stack label
  (for example, `cit-hep-v1`). Recorded with runs and included in their reuse key;
  change it when tools change to avoid reusing results from the previous stack.
  It does not verify an image, require a registry ID, or affect authentication.
  If unset, the label is `unversioned-local-stack`; tool upgrades are not detected
  automatically.

CIT's tested MadGraph setting is `delphes_path = /opt/conda/envs/hep/bin/`.
CIT must bake it into `MG5_aMC/input/mg5_configuration.txt`. Existing Conda
compiler/Pythia/LHAPDF/FastJet settings should be preserved. The application already
generates 1,000 events by default, permits explicit changes up to 10,000, and writes
the selected count into its MadGraph commands. CIT's standalone run-card template
default of `1000 = nevents` is a separate pending image change.

Existing CIT detector cards resolve from FINDINGZ_CARD_ROOT=/opt/conda/envs/hep,
while Delphes itself is in bin/. Packaged custom cards go in
`findingz/resources/cards/`; unset the root override to prefer those over legacy
Delphes-directory cards. See that directory's README for provenance and constraints.
Do not silently substitute a different detector when a card is missing.

## Course updates and release workflow

Application changes require updating the Finding Z checkout and reinstalling
with `python -m pip install '.[hep]'` in `hep`, then restarting the app.
For an image-installed application, CIT should apply this in its image build.
Pushing to GitHub or syncing course materials with nbgitpuller does not update an
already-installed application.

Course files are read from configured external paths, not installed into Python.
Pull/sync the course repository on CIT to publish configuration changes; a GitHub
commit alone does not refresh a mounted checkout. Preserve student-edited notebooks:
copy missing templates only or publish new versioned filenames. Package defaults
are examples for standalone use, not the authoritative course configuration.

Run tests and build a wheel before tagging a release. Test that same wheel locally
and in CIT: MadGraph-only, full pipeline/ROOT, plotting, Jupyter, and persistence.
The repository layout and unit tests do not establish CIT end-to-end compatibility.

The export includes one fallback notebook template solely for the existing local
Docker startup. The course repository is the authoring location after handoff.
The source checkout also retains the existing small synthetic CSVs, example
catalog and course-note fixtures for regression tests. They are not included in
the installed Python wheel and are not the centrally released course datasets.
No new custom detector physics is introduced in this change.

## Licensing / publication gate

MIT is approved for original project material. The LICENSE attribution, "Prateek Agrawal, UCSB", was selected by the instructor; institutional authority still needs confirmation. Read
PROVENANCE.md, THIRD_PARTY_NOTICES.md and docs/licensing/RELEASE-CHECKLIST.md.
Confirm ownership/authority and finish upstream
notices before publishing. Repository owner, names and visibility need approval.
The exported trees are snapshots for initial handoff, not separate local/CIT forks.
Once adopted as repositories, develop the application only in the Finding Z repo.
