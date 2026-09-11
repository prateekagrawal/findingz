# Finding Z detector cards

Place approved, tested, self-contained custom detector cards here. Catalog paths
use `cards/<filename>.tcl`. These files are included in the installed package.
No new physics detector model is supplied by this layout change.

Resolution order: explicit FINDINGZ_CARD_ROOT (authoritative), packaged card,
then the legacy Delphes installation. For CIT's existing cards set the root to
`/opt/conda/envs/hep`, not its `bin` directory. To use a packaged custom card,
unset that override and select its catalog filename.

Custom cards must be self-contained: auxiliary `source` files are not copied into
the process directory by this integration. Retain upstream license notices and
document changes if adapting Delphes cards. Adding a custom filename here alone
does not establish its physics validity or redistribution clearance.

The chosen card is copied into each run and adapted for standard/advanced output.
Explicit/packaged card contents contribute to run identity, so editing a card
does not silently reuse an older sample. Use the toolchain image identifier to
distinguish changes to legacy installation cards/tool versions.
