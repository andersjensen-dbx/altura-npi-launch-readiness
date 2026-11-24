#!/usr/bin/env bash
# Wrapper: use local terraform (bundled TF key can expire) and the demo target.
set -euo pipefail
cd "$(dirname "$0")/.."
export DATABRICKS_TF_EXEC_PATH=/opt/homebrew/bin/terraform
export DATABRICKS_TF_VERSION=$(terraform version -json | jq -r .terraform_version)
export DATABRICKS_TF_CLI_CONFIG_FILE=/dev/null
unset DATABRICKS_CONFIG_PROFILE
databricks bundle "$@" -t "${TARGET:-demo}"
