#!/bin/bash
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Scan all images for vulnerabilities
#
# Usage: scan.sh <tag> <registry> or scan.sh
#

TAG=$1
REGISTRY=$2

# Kubeflow container images scan
echo "Scan container images for Kubeflow"
REPO_DIR="kubeflow"
# if not specified, TAG is taken from corresponding version.txt
TAG=${TAG:-$(eval "cat $REPO_DIR/version.txt")}
# if not specified, setup default registry
REGISTRY=${REGISTRY:-"charmedkubeflow"}

echo "Registry: $REGISTRY"
echo "Tag: $TAG"

IMAGE_LIST=($(docker images $REGISTRY/*:$TAG | awk 'NR>1 {print $1, $2}' | sed 's/ /:/g'))
for IMAGE in "${IMAGE_LIST[@]}"; do
    TRIVY_REPORT="trivy-report-fixed-cve-$IMAGE.txt"
    TRIVY_REPORT=$(echo $TRIVY_REPORT | sed 's/\//-/g' | sed 's/:/-/g')
    docker run -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image --ignore-unfixed $IMAGE > $TRIVY_REPORT
done

# End of Kubeflow container images scan