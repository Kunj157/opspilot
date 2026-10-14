#!/usr/bin/env bash
# Re-pin every Dockerfile base image to the current digest of its tag.
# Base images are pinned (FROM image:tag@sha256:...) so builds are
# reproducible; run this to take in base-image fixes, then rebuild and scan.
#   scripts/pin-base-images.sh
set -euo pipefail

for dockerfile in apps/api/Dockerfile apps/web/Dockerfile demo/services/Dockerfile; do
  for image in $(awk '/^FROM /{print $2}' "$dockerfile" | sed 's/@sha256:.*//' | sort -u); do
    digest="$(docker buildx imagetools inspect "$image" --format '{{json .Manifest}}' | jq -r .digest)"
    sed -i -E "s#^FROM ${image}(@sha256:[0-9a-f]+)?( |\$)#FROM ${image}@${digest}\\2#" "$dockerfile"
    echo "$dockerfile: $image@$digest"
  done
done
