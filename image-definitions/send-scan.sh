#!/bin/bash
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Usage:
#  send-scan.sh <directory-with-scan-results> <jira-token>
#
set -e

DIR=$1
JIRA_TOKEN=$2
if [ -z $DIR ]
then
    echo "ERROR: Directory with scan results is not specified."
    echo "Usage: send-scan.sh <directory-with-scan-results> <jira-token>"
    exit
fi
if [ -z $JIRA_TOKEN ]
then
echo "ERROR: Token is not specified."
    echo "Usage: send-scan.sh <directory-with-scan-results> <jira-token>"
    exit
fi

# get script that sends scan results from Kubeflow CI repo
CI_REPO="https://github.com/canonical/kubeflow-ci.git"
mkdir -p kubeflow-ci
cd kubeflow-ci
git init -q
git remote add -f origin "$CI_REPO" &> /dev/null
git sparse-checkout set scripts/cve-reports/send-scan.py
git pull -q origin main
cd -

# send scans from supplied directory
./kubeflow-ci/scripts/cve-reports/send-scan.py --report-path="$DIR" --jira-url="https://automation.atlassian.com/pro/hooks/$JIRA_TOKEN"

echo "Done."
