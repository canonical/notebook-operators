#!/bin/bash
#
# This script returns list of container images that are managed by this charm and/or its workload
#
# dynamic list
IMAGE_LIST=()
IMAGE_LIST+=($(find . -type f -name metadata.yaml -exec yq '.resources | to_entries | .[] | .value | ."upstream-source"' {} \;))
IMAGE_LIST+=($(yq '.options | .jupyter-images | .default' charms/jupyter-ui/config.yaml | yq '.[]'))
IMAGE_LIST+=($(yq '.options | .rstudio-images | .default' charms/jupyter-ui/config.yaml | yq '.[]'))
IMAGE_LIST+=($(yq '.options | .vscode-images | .default' charms/jupyter-ui/config.yaml | yq '.[]'))
printf "%s\n" "${IMAGE_LIST[@]}"
