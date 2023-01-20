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

# if not specified, setup default registry
REGISTRY=${REGISTRY:-"charmedkubeflow"}

# Kubeflow container images build
echo "Build image definitions for Kubeflow"
REPO_DIR="kubeflow"
# if not specified, TAG is taken from corresponding version.txt
TAG=${TAG:-$(eval "cat $REPO_DIR/version.txt")}

echo "Registry: $REGISTRY"
echo "Tag: $TAG"

echo "Build example-notebook-servers"
cd $REPO_DIR/components/example-notebook-servers
export TAG=$TAG
export REGISTRY=$REGISTRY
make docker-build-all
cd -

echo "Build Jupyter UI"
cd $REPO_DIR/components/crud-web-apps/jupyter
export IMG=jupyter-web-app
make docker-build TAG=$TAG
cd -

echo "Build Jupyter controller"
cd $REPO_DIR/components/notebook-controller
export IMG=notebook-controller
make docker-build TAG=$TAG
cd -

# End of Kubeflow container images build

echo "Docker images ready"
docker images

echo "Done."
