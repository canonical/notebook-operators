#!/bin/bash
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Usage:
#  send-scan.sh <directory-with-scan-results>
#
set -e

DIR=$1
if [ -z $DIR ]
then
    echo "ERROR: Directory with scan results is not specified."
    echo "Usage: send-scan.sh <directory-with-scan-results>"
    exit
fi

# get script that sends scan results from Kubeflow CI repo
CI_REPO="https://github.com/canonical/kubeflow-ci.git"
BRANCH=kf-942-gh188-feat-auto-build-and-scan
mkdir -p kubeflow-ci
cd kubeflow-ci
git init -q
git remote add -f origin "$CI_REPO" &> /dev/null
git sparse-checkout set scripts/send-scan.py
git pull -q origin $BRANCH
cd -

# send scans from supplied directory
./kubeflow-ci/scripts/send-scan.py $DIR

echo "Done."
