# Third-party inventory — incomplete, not a release notice bundle

Audit date: 2026-09-09. Do not use this draft as redistribution clearance.
Exact upstream license texts and any required corresponding source must accompany
the final release as determined with CIT. Links and package names alone are not
a substitute. No third-party component is relicensed by Finding Z.

## Scientific and system components

| Component | Evidence/version | Remaining work |
| --- | --- | --- |
| ROOT and base image | Dockerfile: `rootproject/root:6.34.00-ubuntu24.04` | Record final digest; retain ROOT and bundled-component notices and base OS inventory. |
| MadGraph5_aMC | Dockerfile tag `v3.5.13`; archived commit in linked inventory | Extract licenses from the exact checkout, including bundled libraries and models; review generated-code distribution. |
| Pythia | Installed by MadGraph, not independently version-pinned in Dockerfile | Verify installed version, archive source/checksum and license texts. |
| Delphes | Installed by MadGraph, not independently version-pinned in Dockerfile | Verify version, retain COPYING and notices, including detector cards and bundled components. |
| FastJet, HepMC and other toolchain support | Potentially installed/bundled through upstream installers | Enumerate actual files/versions; do not treat the parent package's license as covering everything. |
| Standard Model UFOs; PDF tables/sets | Models selected through MadGraph; parton inputs may be bundled or downloaded | Identify exact models/tables shipped, their source and applicable notices. |
| Ghostscript and fonts | Current Dockerfile installs Ghostscript through apt for diagram rendering | Extract exact package copyright/license files, including installed fonts and libraries. |
| Ubuntu packages and build tools | Historical dpkg list available | Refresh final image inventory and collect `/usr/share/doc/*/copyright` and referenced license texts; review binary/source obligations. |

ROOT's [official licensing page](https://root.cern/about/license/) describes ROOT
as LGPL 2.1-or-later and identifies separately licensed components, including
MathMore and RooFit. Verify which components the final image includes.
The [Delphes upstream COPYING file](https://github.com/delphes/delphes/blob/master/COPYING)
is a reference only; collect the version actually installed, not just the current
default-branch file. Other license identifications remain unverified here rather
than being inferred from package names.

## Python dependencies

Direct runtime declarations in `pyproject.toml`:

- matplotlib >=3.9; numpy >=2.0; pandas >=2.2; pydantic >=2.9;
  PyYAML >=6.0; streamlit >=1.40.
- Notebook extra: ipywidgets >=8.1; jupyterlab >=4.2.
- HEP extra: awkward >=2.8; uproot >=5.6; vector >=1.6.
- Development extra: pytest >=8.3; ruff >=0.8 (not requested by the image's pip install).

The image also installs setuptools/wheel/pip and many transitive distributions,
including ipykernel, debugpy, Jupyter server/client, pyzmq and plotting libraries.
For every installed distribution, record name/version, metadata license fields,
upstream URL, and shipped license/notice files. Metadata is evidence, not a
complete legal review; inspect vendored code, compiled-wheel libraries and
frontend JavaScript assets as well. The list below is not a full SBOM.

Historical full inventories, copied from the September 3 handoff ZIP:

- [Python packages](docs/licensing/archived-2026-09-03/python-packages.txt)
- [System packages](docs/licensing/archived-2026-09-03/system-packages.txt)
- [MadGraph commit](docs/licensing/archived-2026-09-03/madgraph-commit.txt)

These must be regenerated for the image CIT actually builds. JupyterHub single-user
support and any server-proxy integration added for CIT also need inventory entries.

## Required final evidence

For each redistributed component: exact version/digest, source URL and revision,
license text and notices, modifications if any, and review of any source-delivery
requirements. Keep original notices in installed trees and provide a consolidated
review bundle. The MIT license for project-authored files does not replace
any of these component licenses.
