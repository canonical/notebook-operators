#!/bin/bash
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Build all images
#
# Usage: build.sh <tag> <registry> or build.sh
#

TAG=$1
REGISTRY=$2

# if not specified, TAG is taken from corresponding version.txt
# setup default registry
REGISTRY=${REGISTRY:-"charmedkubeflow"}

echo "Build image-definitions"
echo "Registry: $REGISTRY"
echo "Tag: $TAG"

REPO_DIR="kubeflow"

echo "Build container images for $REPO_DIR/"
TAG=${TAG:-$(eval "cat $REPO_DIR/version.txt")}

echo "Build example-notebook-servers"
cd $REPO_DIR/components/example-notebook-servers
export TAG=$TAG
export REGISTRY=$REGISTRY
make docker-build-all
cd -

echo "Build Jupyter UI"
cd $REPO_DIR/components/crud-web-apps/jupyter
export IMG=$REGISTRY/jupyter-web-app
make docker-build TAG=$TAG
cd -

echo "Build Jupyter controller"
cd $REPO_DIR/components/notebook-controller
export IMG=$REGISTRY/notebook-controller
make docker-build TAG=$TAG
cd -

echo "Docker images ready"
docker images

echo "Done."
