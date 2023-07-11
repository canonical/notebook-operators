#!/bin/bash
#
# This script returns list of container images that are managed by this charm and/or its workload
#
# static list
STATIC_IMAGE_LIST=(
)
# dynamic list
# TO-DO uncomment for production
#git checkout origin/track/1.7
IMAGE_LIST=()
IMAGE_LIST+=($(yq '.spawnerFormDefaults | .image | .options | values[]' charms/jupyter-ui/src/spawner_ui_config.yaml))
IMAGE_LIST+=($(yq '.spawnerFormDefaults | .imageGroupOne | .options | values[]' charms/jupyter-ui/src/spawner_ui_config.yaml))
IMAGE_LIST+=($(yq '.spawnerFormDefaults | .imageGroupTwo | .options | values[]' charms/jupyter-ui/src/spawner_ui_config.yaml))

printf "%s\n" "${STATIC_IMAGE_LIST[@]}"
printf "%s\n" "${IMAGE_LIST[@]}"
