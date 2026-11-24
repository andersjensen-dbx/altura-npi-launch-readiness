#!/usr/bin/env bash
# Convert a jupytext percent-script notebook to .ipynb and execute it locally against
# Databricks serverless (Databricks Connect), saving outputs in place as execution evidence.
# Fails (exit 1) and prints the failing cell if any cell raised an error.
set -euo pipefail
cd "$(dirname "$0")/.."
export DATABRICKS_CONFIG_PROFILE="${NPI_PROFILE:-fevm-andersjensen-fevm-3}"
export MLFLOW_USE_DATABRICKS_SDK_MODEL_ARTIFACTS_REPO_FOR_UC=true  # UC model artifacts via Databricks SDK (no cloud SDKs needed locally)
for src in "$@"; do
  nb="${src%.py}.ipynb"
  uv run jupytext --to ipynb --set-kernel python3 -o "$nb" "$src" >/dev/null
  (cd "$(dirname "$nb")" && uv run jupyter nbconvert --to notebook --execute --inplace --allow-errors \
     --ExecutePreprocessor.timeout=3600 "$(basename "$nb")" 2>/dev/null)
  if uv run python tools/nb_error.py "$nb" | grep -q .; then
    echo "FAILED: $nb"; uv run python tools/nb_error.py "$nb"; exit 1
  fi
  echo "executed: $nb"
done
