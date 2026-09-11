#!/usr/bin/env bash
set -euo pipefail

workspace_notebooks="/workspace/notebooks"
mkdir -p "$workspace_notebooks"

for template in /opt/findingz/notebooks/*.ipynb; do
    destination="$workspace_notebooks/$(basename "$template")"
    if [[ ! -e "$destination" ]]; then
        cp "$template" "$destination"
    fi
done

# A versioned destination lets an existing student workspace receive the redesigned
# hypothesis notebook without overwriting an edited legacy cut-and-count notebook.
hypothesis_notebook="$workspace_notebooks/04_hypothesis_analysis.ipynb"
if [[ ! -e "$hypothesis_notebook" ]]; then
    cp /opt/findingz/notebooks/04_cut_and_count.ipynb "$hypothesis_notebook"
fi

# Keep existing student notebooks immutable while releasing the object-definition
# revision under a new starter name.
object_notebook="$workspace_notebooks/05_hypothesis_and_object_analysis.ipynb"
if [[ ! -e "$object_notebook" ]]; then
    cp /opt/findingz/notebooks/04_cut_and_count.ipynb "$object_notebook"
fi

# Release a current starter while preserving every existing student notebook.
current_notebook="$workspace_notebooks/06_sample_analysis.ipynb"
if [[ ! -e "$current_notebook" ]]; then
    cp /opt/findingz/notebooks/04_cut_and_count.ipynb "$current_notebook"
fi

exec python -m jupyterlab \
    --ip=0.0.0.0 \
    --port=8888 \
    --no-browser \
    --IdentityProvider.token= \
    --PasswordIdentityProvider.hashed_password=
