#!/bin/bash
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Setup image definitions based on upstream.
#
# Create directory and checkout specified components from upstream repositories.
# The directory specified below should not exist in <local-directory>.
# Updated upstream version of component is checked out from specified branch and then all git
# information is deleted, leaving only the resouces required for image definitions.
# Use this script in setting up new image definitions or creating a copy to check for
# differences between existing image definitions and upstream vesions.
# This script should be specific for the charm repository.
#
# Usage:
#  setup.sh <local-directory>
#

DIR=$1
if [ -z $DIR ]
then
    echo "ERROR: Local directory is not specified."
    echo "Usage: setup.sh <local-directory>"
    exit
fi

# Kubeflow image definitions setup
echo "Setup image definitions for Kubeflow based on upstream"
LOCAL_REPO_DIR="kubeflow"
REMOTE_REPO="https://github.com/kubeflow/kubeflow.git"
BRANCH=master

echo "Remote repository: $REMOTE_REPO"
echo "Local directory: $DIR/$LOCAL_REPO_DIR"
echo "Branch: $BRANCH"

# if directory already exists do not proceed
if [ -d "$LOCAL_REPO_DIR" ]
then
    echo "Specified directory $LOCAL_REPO_DIR already exists."
    exit
fi

# setup local directory
mkdir -p $LOCAL_REPO_DIR
cd $LOCAL_REPO_DIR
git init -q
git remote add -f origin "$REMOTE_REPO" &> /dev/null

# components to pull from upstream
COMPONENTS_LIST=(
"components/example-notebook-servers/base"
"components/example-notebook-servers/jupyter-pytorch-full"
"components/example-notebook-servers/jupyter-pytorch"
"components/example-notebook-servers/jupyter-scipy"
"components/example-notebook-servers/jupyter-tensorflow-full"
"components/example-notebook-servers/jupyter-tensorflow"
"components/example-notebook-servers/jupyter"
"components/example-notebook-servers/Makefile"
"components/crud-web-apps/jupyter"
"components/crud-web-apps/common"
"components/common"
"components/notebook-controller"
)

# perform sparse checkout for the specified components
SPARSE_CHECKOUT_DIRS=""
for COMPONENT in "${COMPONENTS_LIST[@]}"; do
	SPARSE_CHECKOUT_DIRS+="$COMPONENT "
done
git sparse-checkout set $SPARSE_CHECKOUT_DIRS
git pull -q origin $BRANCH

# generate version prior to cleaning up git information
git describe --tags --always --dirty  > ./version.txt

# cleanup git
rm -rf .git
cd ..
# End of Kubeflow image definitions setup

echo "Done."
