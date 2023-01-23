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

# get all images that need to be published
IMAGE_LIST=($(docker image ls *:$TAG --format="{{.Repository}}:{{.Tag}}"))

echo $IMAGE_LIST
for IMAGE in "${IMAGE_LIST[@]}"; do
    # tag image with registry and push it
    docker tag $IMAGE $REGISTRY/$IMAGE
    docker push $REGISTRY/$IMAGE
done

# End of Kubeflow container images publish
