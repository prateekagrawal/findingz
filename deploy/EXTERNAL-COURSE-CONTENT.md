# External course models and samples (FindingZ 0.2.0+)

CIT installs FindingZ 0.2.0 or later once, in the `hep` environment. The existing
MadGraph/Pythia/Delphes installation can remain unchanged. Future compatible
course content updates do not require rebuilding that toolchain.

In the course catalogue (paths are relative to the YAML file):

```yaml
schema_version: 1
minimum_findingz_version: "0.2.0"
models:
  my_model:
    label: My physics model
    ufo_path: ../models/my_model
    enabled: true
dataset_folders:
  shared:
    path: ../datasets
    enabled: true
```

These are additions to the existing catalogue, not a complete replacement.
Register processes with `model_ids: [my_model]` and appropriate MadGraph commands.
Specify exactly one of `madgraph_name` (installed model) or `ufo_path`.
Absolute paths also work for CIT-mounted shared storage. This is filesystem
support, not an HTTP/S3 downloader. Ensure paths are visible inside the container.

UFOs are executable Python: only distribute instructor-approved, licensed models.
Python/toolchain compatibility still needs testing, and models requiring new
libraries may require CIT installation. MadGraph working/import paths must not
contain whitespace. UFO directory contents must not use symlinks.

FindingZ hashes model contents for run reuse and keeps a `ufo_model` snapshot
and hash in each new run. Editing a model therefore invalidates reuse. Keep
released model directories immutable during generation. Models and parameter
defaults should be validated before students use them; custom models are not
automatically compatible with every analysis or shower configuration.

Each dataset folder contains immediate child run directories, each with its
original run ID as directory name, `manifest.json`, and the analysis file named
by `stages.analysis` (normally `analysis.csv`). Copy complete FindingZ run folders
to retain ROOT/LHE, cards and other provenance as well. Do not rename run IDs.
Run labels, cross sections and generated-event counts come from the manifest.
Unfinished runs are not listed; shared folders are only read, never copied into
the student's run root or deleted by local run management. Avoid duplicate run
IDs; a student's local copy takes precedence over an identical shared run ID.

Manifest versions 1 and 2 are supported (missing version means legacy v1).
Unknown shared-manifest versions fail explicitly. New HEP manifests record
`findingz_version`; the catalogue's minimum version guards new features on
updated installations. Older FindingZ releases predate that guard: install the
0.2.0 app before publishing catalogues that use these additions. Pin/test app
releases and retain original samples; no automatic dataset migrations are made.
