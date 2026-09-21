# Helpers for later analyses

Start with the explicit introductory notebook: inspect its Boolean masks, event
weights and Poisson calculation first. The following helpers package those same
steps when repeating an analysis across many samples or selections. They are not
required in the introductory notebook.

```python
from findingz.notebook_analysis import (
    available_samples, sample_table, select_samples, plot_samples,
    compare_samples, comparison_table,
)
library = available_samples()
sample_table(library)  # copy IDs from this table
```

- `available_samples()` locates accessible personal and shared FindingZ runs.
- `sample_table(library)` returns a pandas table of IDs and normalization metadata.
- `select_samples(library, ids, cuts={"mll": (80, 100)}, channels=["ee"],
  luminosity_fb=0.00002)` returns a dictionary of selected DataFrames. Range
  boundaries are inclusive. `channels=None` keeps all; `[]` selects none.
  `luminosity_fb=None` leaves simulation weights unscaled. Otherwise weights are
  multiplied by cross section [pb] × luminosity [fb⁻¹] × 1000 / generated events.
- `plot_samples(frames, library, "mll", shape_only=True)` returns a Matplotlib
  figure and a yield table. It uses 40 common bins; shape normalization divides
  selected weights by their sum. Display the returned figure explicitly.

```python
# Replace these with two compatible sample IDs from sample_table.
null_id = "run:YOUR_QED_RUN"
alternative_id = "run:YOUR_SM_RUN"
result = compare_samples(
    library, null_id, alternative_id,
    cuts={"mll": (80, 100)}, channels=["ee"],
    luminosity_fb=0.00002, null_uncertainty=0.0,
)
comparison_table(result)
```

`compare_samples` applies identical selections, normalizes the complete null and
alternative predictions, and returns a `HypothesisComparison` object:
`null_yield`, `alternative_yield`, `difference`, `signed_significance` and
`null_uncertainty_fraction`. It never adds the two predictions. Missing roles
return `None`; missing samples, incompatible configurations and invalid weights
raise errors. Configuration checks do not establish physical comparability.

`comparison_table(result)` only formats those values as a pandas Series. It does
not apply cuts or recalculate statistics. For `None`, it shows a selection prompt.

The significance is signed Asimov Poisson sensitivity, not an exact observed
p-value. A nonzero fractional null uncertainty profiles a Gaussian-constrained
null rate. Zero null yield gives `None`, not infinity. Finite simulation
uncertainties are not included. Use the explicit notebook to understand these
assumptions before using the shortcut.

Both selection and plotting accept `variables=` with saved variable definitions
when reproducing an export. Otherwise they use the live course variable catalogue.
Old `count_samples` / `count_table` are legacy additive helpers; do not use them
for complete null-versus-alternative comparisons.
