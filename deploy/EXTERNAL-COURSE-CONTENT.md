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

## Card customization (0.2.0 candidate, catalogue schema 2)

Existing schema-1 catalogues remain supported with their existing behavior.
Catalogues that enable card customization must use `schema_version: 2`. This
allows releases that only understand schema 1 to reject the new catalogue rather
than silently ignore its physics settings. Install and test this candidate before
deploying the updated course catalogue; the version number alone does not identify
which development build is installed. Record the commit as well.

```yaml
schema_version: 2
minimum_findingz_version: "0.2.0"
run_card:
  defaults: {}                 # no extra cuts unless explicitly specified
  editable: [ptl, etal, drll, mmll, mmllmax]
param_card:
  defaults: {}
  editable: []                 # usually enabled for a particular model
shower_card:
  editable: true
  # path: ../cards/pythia8_card.dat
detector_card:
  editable: true
  # path: ../cards/delphes_card.tcl
```

These blocks extend a complete catalogue. A process's block replaces the
course-wide block of the same name; an explicit empty block disables that
customization for the process. Parameter-card policy may also be set on a model:
the precedence is process, model, course. For example, add this to `models.sm`:

```yaml
param_card:
  defaults: {}
  editable: ["mass 23", "decay 23", "sminputs 1"]
```

The run and parameter editors show clickable chips for course-authorized entries.
Selected chips are highlighted. Each selected entry adds one compact row with its
name, editable value, effective default, and description. Optional `descriptions`
mappings in run/parameter policies override the built-in descriptions.
Course defaults take precedence; other defaults are read from cards prepared by
MadGraph for the selected model and process. This preparation generates no events
and is cached for the process/model/toolchain, including an external UFO content
hash. Changing a model or process therefore refreshes the displayed defaults.

Run values may be numbers, booleans or single text tokens; parameter values must
be finite numbers. Parameter names remain SLHA targets such as `mass 23`,
`decay 23`, `sminputs 1`, or `nmix 1 2`. Blank values, deselecting an entry, or
resetting restore defaults. Merely selecting an entry does not create an override.
Values and defaults appear side by side for comparison before generation. Invalid values block
submission. Neither editor executes student-supplied MadGraph commands.
Entries must exist in the generated native card, otherwise generation stops with
an explicit error. Entries marked dependent in the parameter card are rejected;
edit their independent inputs instead. A restricted UFO may fix parameters that
cannot be changed meaningfully without selecting a different model restriction.
Automatic widths and branching-fraction editing are not part of this editor.

Event count, random seed, beam energies and beam types retain their existing
controls and cannot be overridden a second time through run-card edits.

Pythia and Delphes editors appear for full-pipeline runs. Optional course paths
are relative to the catalogue file, and the files must be available on the same
filesystem as FindingZ. Without a course path, the Pythia editor starts from the
installed MadGraph Pythia8 template; the detector editor starts from the selected
detector with the chosen output profile applied. Opening an editor without
changing its text preserves the default run identity. A custom detector card is
used verbatim, including its branch choices. Cards are single text files: any
included files must already be available on the toolchain's filesystem. Keep
`Main:numberOfEvents = -1` and `HEPMCoutput:file = hepmc` or `hepmc.gz`; FindingZ
needs the full showered sample and its output for normalization and extraction.
Cards and model settings must be compatible with the installed tools; changing
course content does not install new plugins, PDF sets, or external libraries.

All requested card changes enter the run identity and manifest. Native cards
after generation are retained under `cards/generated/`; requested run/parameter
and shower cards are also saved separately. No edits are made to installed model
or toolchain defaults. Existing samples remain readable, and empty customizations
preserve existing run IDs. Counting requires the same collision setup and analysis
level, plus usable normalization. Differences in generation settings (including
PDFs, scales and cuts), shower/detector cards, detector presets or output profiles
produce a compact warning and do not remove samples from the selection menu.
Different model parameters remain comparable hypotheses. Saved effective run cards
are compared when available; missing cards are flagged as incomplete information.
The check does not attempt to prove that arbitrary generation cuts cover an analysis
region or that background samples are disjoint. Students must assess those conditions.

## Terminal and Python runs

The `hep` environment already supplies MadGraph. Running through FindingZ's Python
pipeline also produces the manifest and analysis files the UI needs. For example:

```python
import os
from findingz.hep_pipeline import HepSimulationConfig, run_hep_simulation

config = HepSimulationConfig(
    label="Scripted QED run",
    collider="ee", collider_id="markii29", beam_energy_gev=14.5,
    model="sm", process="ee_mumu_qed",
    process_lines=["generate e- e+ > mu- mu+ / z h"],
    run_mode="madgraph", events=1000, seed=225,
    run_card_overrides={"ptl": 5.0},
    param_card_overrides={"sminputs 1": 137.035999},
)
run = run_hep_simulation(config, os.environ["FINDINGZ_RUN_ROOT"])
print(run.run_dir)
```

Use the same run root as the app, or register the output parent under
`dataset_folders`. Such samples appear in FindingZ after refreshing. Scripts use
the same pipeline as the app; the example explicitly supplies its settings rather
than reading the catalogue's defaults. For full runs, `shower_card_text` and
`detector_card_text` accept the contents of custom files as Python strings.

A raw `mg5_aMC`/`madevent` output directory is **not** imported automatically.
An importer still needs to recover event counts, cross sections, cards and beam
metadata, construct the analysis data, and write a FindingZ manifest. The current
automatic extraction and analysis are for opposite-sign electron/muon pairs;
arbitrary final states or weighted/NLO samples need additional analysis/import
support. Do not label raw outputs as compatible simply by adding a manifest.

## Basic object analyses

New runs keep one analysis row per event, including events without an opposite-sign
same-flavour electron/muon pair (`channel: other`). Existing dilepton columns and
pair choices are preserved; they are undefined for events without a pair. Select
`ee`/`mumu` or apply a dilepton-variable cut when counting a dilepton selection.
Previously saved samples remain readable, but their discarded events cannot be
recovered from the CSV. The analysis schema enters new run identities.

`analysis_variables.yaml` controls the offered columns and per-process lists.
The default list now includes electron, muon, photon and jet multiplicities,
leading/subleading pT and eta, leading-pair masses, and Delphes MET. Missing
collections are unavailable, not treated as zero; a present empty collection has
count zero and undefined object kinematics. Explicit kinematic cuts exclude
undefined values. Existing process-specific variable lists stay restricted.

MadGraph-only summaries expose final quarks/gluons as `parton`, not reconstructed
jets. They do not provide detector MET. Detailed clustering, reconstruction and
custom analyses belong in Jupyter using the retained ROOT/LHE files. Custom
Delphes cards must retain the object branches needed for the desired summaries.

## Beam presets

`beam_type` accepts `pp`, `ee`, `mumu`, `ep`, `pe`, and `ppbar`.
`beam_energy_gev` is the beam-1 energy; optional `beam2_energy_gev` sets
beam 2 independently. If omitted, both energies are equal. Displayed sqrt(s)
uses the ultrarelativistic head-on expression `2*sqrt(E1*E2)`.
The two beam energies also enter sample compatibility and run identity.

MadGraph `lpp1,lpp2` are respectively `(1,1)`, `(0,0)`, `(0,0)`, `(0,1)`,
`(1,0)`, `(1,-1)`. Elementary beams have no beam PDFs in these presets.
Process cards must specify the matching incoming particles in beam order:
`mu- mu+`, `e- p`, or `p e-`, for example. For proton–antiproton inclusive
processes use the usual `p p` parton multiparticles; `lpp2=-1` supplies the
antiproton PDFs. Positron–proton processes can use `e+ p` with the `ep` preset.
Beam spectra, beamstrahlung and lepton PDFs are not supplied automatically.

Enable `full_pipeline` only with a suitable shower and detector configuration;
the beam preset does not supply a detector model. The temporary course test
catalogue includes MadGraph-only muon, HERA-like and Tevatron-like examples.

Card value controls follow the native default type: booleans use toggles, numeric
values use number fields, and other tokens use text inputs. `pdlabel` lists
installed built-in PDF grids and the detected LHAPDF provider. `lhaid` lists
installed LHAPDF central members by set name and ID (no automatic downloads).
An unavailable default LHAPDF ID must be replaced before using LHAPDF.
Fixed-scale values and LHAPDF IDs are inactive when their controlling setting
is off. Inactive student edits are not submitted.

A policy can restrict choices or supply readable labels with a `choices` mapping:

```yaml
run_card:
  editable: [pdlabel]
  choices:
    pdlabel:
      nn23lo1: NNPDF 2.3 LO
      lhapdf: Installed LHAPDF sets
```

For PDF fields these choices are intersected with installed capabilities.
Other run or parameter entries can also supply string-valued choice-to-label
mappings; values are validated with the usual card parsers.
