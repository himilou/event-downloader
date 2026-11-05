#!/usr/bin/env bash
# Builds and pushes image to dockerhub as public image
# Execute with bash; Docker Hub login must already be configured.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname -- "$SCRIPT_DIR")"
IMAGE="${IMAGE:-himilou/luckypythontasks:Prod1-1}"

docker build --platform linux/amd64 --file "$PROJECT_ROOT/Dockerfile" --tag "$IMAGE" "$PROJECT_ROOT"
docker push "$IMAGE"
echo "Published $IMAGE"
