#!/bin/bash
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Scan all images for vulnerabilities
#
# Usage: scan.sh <tag> or scan.sh
#
set -e

TAG=$1
REPORT_TOTALS=false
TRIVY_REPORTS_DIR="trivy-reports"
TRIVY_REPORT_TYPE="json"

if [ -d "$TRIVY_REPORTS_DIR" ]; then
    echo "WARNING: $TRIVY_REPORTS_DIR directory already exists. Some reports might not be generated."
    echo "         To scan all images remove $TRIVY_REPORTS_DIR directory."
fi

# Kubeflow container images scan
echo "Scan container images for Kubeflow"
REPO_DIR="kubeflow"
# if not specified, TAG is taken from corresponding version.txt
TAG=${TAG:-$(eval "cat $REPO_DIR/version.txt")}
KF_PATCH_COMMIT=$(eval "cat ./kubeflow-patch-commit.txt")
DATE=$(date +%F)
SCAN_SUMMARY_FILE="scan-summary.txt"
if [ ! -f $SCAN_SUMMARY_FILE ]; then
    # create header for scan summary file, if it does not exist
    echo "Tag: $TAG" > $SCAN_SUMMARY_FILE
    echo "Date: $DATE" >> $SCAN_SUMMARY_FILE
    echo "CVEs per image:" >> $SCAN_SUMMARY_FILE
    echo " IMAGE | BASE | CRITICAL | HIGH | MEDIUM | LOW " >> $SCAN_SUMMARY_FILE
    echo " -- | -- | -- | -- | -- | -- " >> $SCAN_SUMMARY_FILE
fi

# create directory for trivy reports
mkdir -p "$TRIVY_REPORTS_DIR"

# get all images that are available for scanning
# excluded:
# - tagged with `<none>`
# - aquasec/trivy repository (scanner)
IMAGE_LIST=($(docker images --format="{{json .}}" | jq -r 'select((.Tag=="$TAG") or (.Tag!="<none>" and .Tag!="$TAG-$KF_PATCH_COMMIT" and .Repository!="aquasec/trivy")) | "\(.Repository):\(.Tag)"'))

# for every image generate trivy report and store it in `$TRIVY_REPORTS_DIR/` directory
# '.', ':' and '/' in image names are replaced with '-' for files
for IMAGE in "${IMAGE_LIST[@]}"; do
    # trivy report name should contain artifact name being scanned with where '.', ':' and '/' replaced with '-'
    TRIVY_REPORT="$IMAGE"
    TRIVY_REPORT=$(echo $TRIVY_REPORT | sed 's/:/-/g')
    TRIVY_REPORT=$(echo $TRIVY_REPORT | sed 's/\//-/g')
    TRIVY_REPORT=$(echo $TRIVY_REPORT | sed 's/\./-/g')
    TRIVY_REPORT=$(echo "$TRIVY_REPORTS_DIR/$TRIVY_REPORT.$TRIVY_REPORT_TYPE")
    if [ -f "$TRIVY_REPORT" ]; then
      echo "Trivy report '$TRIVY_REPORT' for $IMAGE already exist, skip it"
      continue
    fi
    echo "Scan image $IMAGE report in $TRIVY_REPORT"
    docker run -v /var/run/docker.sock:/var/run/docker.sock -v `pwd`:`pwd` -w `pwd` aquasec/trivy image --timeout 20m -f $TRIVY_REPORT_TYPE -o $TRIVY_REPORT --ignore-unfixed $IMAGE
    if [ "$TRIVY_REPORT_TYPE" = "json" ]; then
      # for JSON type retrieve severity counts
      NUM_CRITICAL=$(grep CRITICAL $TRIVY_REPORT | wc -l)
      NUM_HIGH=$(grep HIGH $TRIVY_REPORT | wc -l)
      NUM_MEDIUM=$(grep MEDIUM $TRIVY_REPORT | wc -l)
      NUM_LOW=$(grep LOW $TRIVY_REPORT | wc -l)
      BASE=$(cat $TRIVY_REPORT | jq '.Metadata.OS | "\(.Family):\(.Name)"' | sed 's/"//g')
      echo " $IMAGE | $BASE | $NUM_CRITICAL | $NUM_HIGH | $NUM_MEDIUM | $NUM_LOW " >> $SCAN_SUMMARY_FILE
    fi
done

if [ "$REPORT_TOTALS" = true ]; then
    NUM_CRITICAL=$(grep CRITICAL "$TRIVY_REPORTS_DIR/*" | wc -l)
    NUM_HIGH=$(grep HIGH "$TRIVY_REPORTS_DIR/*" | wc -l)
    NUM_MEDIUM=$(grep MEDIUM "$TRIVY_REPORTS_DIR/*" | wc -l)
    NUM_LOW=$(grep LOW "$TRIVY_REPORTS_DIR/*" | wc -l)
    echo "| | Totals: | $NUM_CRITICAL | $NUM_HIGH | $NUM_MEDIUM | $NUM_LOW" >> $SCAN_SUMMARY_FILE
fi
cat $SCAN_SUMMARY_FILE

# End of Kubeflow container images scan
