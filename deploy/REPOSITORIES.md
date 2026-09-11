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
course checkout, persistent run directory, image revision and authenticated notebook
URL, and source it before launch. Do not commit secrets. The UI command is:

```bash
findingz-ui --server.address=127.0.0.1 --server.port=8501
```

CIT should connect its existing Streamlit launcher to this command in `hep`, using
its authenticated proxy and appropriate port/base URL settings. These remain to be
confirmed with CIT; localhost:8501 is not a public hosting configuration.

## Portable settings and cards

- FINDINGZ_CATALOG_PATH: live course catalog (dropdowns, availability, samples).
- FINDINGZ_VARIABLES_PATH: live observable definitions; by default next to catalog.
- FINDINGZ_RUN_ROOT: persistent writable student run storage.
- FINDINGZ_JUPYTER_URL: authenticated notebook link.
- FINDINGZ_MG5, FINDINGZ_PYTHIA8_DIR, FINDINGZ_DELPHES_DIR: installed tool locations.
- FINDINGZ_CARD_ROOT: optional independent root for catalog-relative detector cards.
- FINDINGZ_HEP_IMAGE_ID: actual tested toolchain revision; change when tools change.

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
