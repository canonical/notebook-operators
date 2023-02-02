#!/bin/bash
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Check if repositories were updates since patch and log it
#
# Usage: check.sh
#

# Kubeflow repository check
echo "Check Kubeflow repository"
REPO_DIR="kubeflow"
cd $REPO_DIR
KF_REPO_COMMIT=$(eval "git rev-parse --short HEAD")
KF_PATCH_COMMIT=$(eval "cat ../kubeflow-patch-commit.txt")
if [ $KF_REPO_COMMIT != KF_PATCH_COMMIT ]; then
    echo "WARNING: Repository $REPO_DIR/ has been updated since patch was generated"
    echo "Latest commit $KF_REPO_COMMIT Patch commit $KF_PATCH_COMMIT"
fi

cd -
# End of Kubeflow repository check
