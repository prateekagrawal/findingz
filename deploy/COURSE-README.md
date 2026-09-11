# PHYS 225A — Finding Z course materials

Initial repository layout; MIT selected for original material, not yet published.

- `config/course_catalog.yaml`: models, colliders, processes, detectors and samples.
- `config/analysis_variables.yaml`: plotting and selection variables by process.
- `notebooks/`: editable student analysis templates, including object definitions.
- `datasets/`: dataset documentation; large data live on CIT shared storage.

Point FINDINGZ_CATALOG_PATH and FINDINGZ_VARIABLES_PATH at this checkout. The
application is installed separately from the Finding Z repository in Conda `hep`.
Keep student run outputs and edited notebooks in persistent student storage,
outside the centrally updated checkout. Copy missing templates to student storage
without overwriting existing work. Select available samples explicitly in notebooks.

No prepared event samples are included initially. Register approved complete run
directories in the catalog after storage paths and provenance are agreed. The
notebook counting exercise requires at least two compatible samples.

Instructors may enable/disable entries without rebuilding the Python application.
Updating Git alone is insufficient: CIT must pull/sync the deployed checkout.
Validate edited configurations before release and test selected detector cards.

MIT is approved for original teaching material. LICENSE uses the instructor-selected
attribution "Prateek Agrawal, UCSB"; confirm ownership/authority before publication.
Third-party material retains its upstream terms. Do not add private course records, student submissions, credentials,
or third-party data without the appropriate permission and provenance.
