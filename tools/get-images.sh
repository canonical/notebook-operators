#!/bin/bash
#
# This script returns list of container images that are managed by this charm and/or its workload
#
# dynamic list
IMAGE_LIST=()
IMAGE_LIST+=($(find $REPO -type f -name metadata.yaml -exec yq '.resources | to_entries | .[] | .value | ."upstream-source"' {} \;))
IMAGE_LIST+=($(yq '.spawnerFormDefaults | .image | .options | .[]' charms/jupyter-ui/src/spawner_ui_config.yaml))
IMAGE_LIST+=($(yq '.spawnerFormDefaults | .imageGroupOne | .options | .[]' charms/jupyter-ui/src/spawner_ui_config.yaml))
IMAGE_LIST+=($(yq '.spawnerFormDefaults | .imageGroupTwo | .options | .[]' charms/jupyter-ui/src/spawner_ui_config.yaml))
printf "%s\n" "${IMAGE_LIST[@]}"
