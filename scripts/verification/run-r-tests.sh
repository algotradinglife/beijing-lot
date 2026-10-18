#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
# Canonical configured roots; never depend on interactive shell/R startup files.
source config/source-extraction.env
: "${R_LIBS_USER:?Set R_LIBS_USER with the intended installed package library first}"
export BEIDAN_TEST_PYTHON="${BEIDAN_TEST_PYTHON:-${RETICULATE_PYTHON:-$PWD/.venv/bin/python}}"
export RETICULATE_PYTHON="${RETICULATE_PYTHON:-$BEIDAN_TEST_PYTHON}"
exec /opt/R/4.6.1/bin/Rscript --vanilla tests/testthat.R "$@"
