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

# setup default tag and registry
TAG?=$(git describe --tags --always --dirty)
REGISTRY?=charmedkubeflow

echo "Build image-definitions"
echo "Registry: $REGSITRY"
echo "Tag: $TAG"
cd image-definitions

REPO_DIR="kubeflow"

echo "Build container images for $REPO_DIR/"
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

docker images

echo "Done."
