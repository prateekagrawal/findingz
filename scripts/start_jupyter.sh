#!/usr/bin/env bash
set -euo pipefail

# Course originals live in the external course-materials repository, just as on
# CIT. Students copy exercises to their writable work directory before editing.
# Never seed or overwrite notebooks from the app image during server startup.
mkdir -p "${FINDINGZ_NOTEBOOK_DIR:-/workspace/notebooks}"

exec python -m jupyterlab \
    --ip=0.0.0.0 \
    --port=8888 \
    --no-browser \
    --IdentityProvider.token= \
    --PasswordIdentityProvider.hashed_password=
