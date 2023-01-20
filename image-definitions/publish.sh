#!/bin/bash
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Publish all images
#
# Usage: publish.sh <tag> <registry> or publish.sh
#

TAG=$1
REGISTRY=$2

# if not specified, setup default registry
REGISTRY=${REGISTRY:-"charmedkubeflow"}

# Kubeflow container images publish
echo "Publish container images for Kubeflow"
REPO_DIR="kubeflow"
# if not specified, TAG is taken from corresponding version.txt
TAG=${TAG:-$(eval "cat $REPO_DIR/version.txt")}

echo "Registry: $REGISTRY"
echo "Tag: $TAG"

IMAGE_LIST=$(docker images $REGISTRY/*:$TAG | awk 'NR>1 {print $1, $2}' | sed 's/ /:/g')

echo $IMAGE_LIST
for IMAGE in "${IMAGE_LIST[@]}"; do
    # tag image with registry
	echo "docker push $IMAGE"
    #docker push $IMAGE
done

# End of Kubeflow container images publish
