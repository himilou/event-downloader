#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

RESOURCE_GROUP="luckyliquor"
JOB_NAME="luckyliquor-python-tasks"

# Load the project .env, just like the Ruby deployment script.
set -a
source "$SCRIPT_DIR/../.env"
set +a

# List first so an Azure connection failure does not look like a missing job.
EXISTING_JOB="$(az containerapp job list --resource-group "$RESOURCE_GROUP" \
  --query "[?name=='${JOB_NAME}'].name | [0]" -o tsv)"
if [[ -n "$EXISTING_JOB" ]]; then
  az containerapp job update \
    --name "$JOB_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --yaml "$SCRIPT_DIR/python_container_app_job.yaml" \
    --output none
else
  az containerapp job create \
    --name "$JOB_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --yaml "$SCRIPT_DIR/python_container_app_job.yaml" \
    --output none
fi

az containerapp job secret set \
  --name "$JOB_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --secrets drive-api-key="$GOOGLE_DRIVE_API_KEY" \
  --output none

if [[ "${START_JOB:-false}" == "true" ]]; then
  az containerapp job start --name "$JOB_NAME" --resource-group "$RESOURCE_GROUP"
fi
echo "Deployed $JOB_NAME"
