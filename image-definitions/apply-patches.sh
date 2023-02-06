#!/bin/bash
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Apply patches
#
# Usage: apply-patches.sh
#
set -e

# Patch Kubeflow
echo "Apply patch for Kubeflow"
cd ./kubeflow
git apply ../kubeflow.patch
cd -
# End of Kubeflow patch

echo "Done."

