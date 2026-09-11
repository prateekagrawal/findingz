# Licensing release checklist for CIT

Status: DRAFT / NOT CLEARED FOR DISTRIBUTION. Updated 2026-09-09.

## Decisions for instructor / UCSB

- [ ] Confirm who is authorized to license the project and the copyright holder.
- [ ] Confirm institutional and contributor requirements, including earlier-project reuse.
- [x] Instructor approved MIT for original code, notebooks, documentation and
      synthetic teaching samples (2026-09-11).
- [x] Instructor selected attribution: `Prateek Agrawal, UCSB`.
      Institutional authorization remains a separate open review item.
- [ ] Approve the provenance account in `PROVENANCE.md`.

## Technical evidence still required

- [x] Inspect current dependency declarations and upstream-derived detector cards.
- [x] Recover historical Python/system inventories from the September 3 archive.
- [x] Identify synthetic-data provenance and custom-model placeholder status.
- [ ] Start Docker when convenient and inspect the exact image intended for CIT.
- [ ] Record its digest, tool versions, model/PDF contents, and updated package lists.
- [ ] Collect verbatim upstream license/notice files from installed source trees,
      Python distributions, OS packages, fonts and bundled dependencies.
- [ ] Resolve missing/ambiguous licenses and any redistribution/source obligations
      with CIT; do not mark a component cleared solely because it is open source.
- [x] Add MIT LICENSE and package metadata with instructor-selected attribution.
- [ ] Confirm copyright holder/authority before publishing.
- [ ] Finalize THIRD_PARTY_NOTICES with exact-version evidence and include texts.
- [ ] Verify the final archive actually contains the required notices and inventory.

## Proposed minimal deployment manifest

| Material | Proposed placement | Notes |
| --- | --- | --- |
| Application package, app entrypoint and runtime scripts | Image | Original-license review plus dependency inventory. |
| ROOT/MadGraph/Pythia/Delphes and dependencies | Image | Retain all applicable upstream evidence/notices. |
| Course and observable YAML configuration | Mounted course content | Runtime already supports updated catalogs; check mounted paths. |
| Starter notebooks | Copy once to student storage from release templates | Preserve edits; review original-material license. |
| Chosen prepared samples | Read-only course mount | Per-sample provenance; copied cards/code need upstream attribution. |
| Student notebooks and generated runs | Persistent per-user writable storage | Do not bundle private student work into the course image. |
| Legacy synthetic CSVs | Optional | Remove only together with references needing them. |
| Tests, design drafts, unused LLM/demo exercises, archived runs and old image tarballs | Outside minimal runtime bundle | Keep useful source/testing material separately; don't delete working source as part of this audit. |

The current Dockerfile uses `COPY .` and copies starter data into the image. This
table is a proposed cleanup, not a claim that a minimal image has been implemented.
Mounting a file rather than baking it into an image does not by itself resolve its
license/provenance requirements. The September 3 ZIP has not been replaced.
