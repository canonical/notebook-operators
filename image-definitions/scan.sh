#!/bin/bash
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Scan all images for vulnerabilities
#
# Usage: scan.sh <tag> or scan.sh
#

TAG=$1

# Kubeflow container images scan
echo "Scan container images for Kubeflow"
REPO_DIR="kubeflow"
# if not specified, TAG is taken from corresponding version.txt
TAG=${TAG:-$(eval "cat $REPO_DIR/version.txt")}
DATE=$(date +'%Y.%-m.%-d')
SCAN_SUMMARY_FILE="scan-summary-$DATE.txt"
echo "Tag: $TAG" > $SCAN_SUMMARY_FILE
echo "Date: $DATE" >> $SCAN_SUMMARY_FILE

# create directory for trivy reports
mkdir -p trivy-reports

# get all images that are available for scanning
# excluded:
# - tagged with `<none>`
# - aquasec/trivy repository (scanner)
IMAGE_LIST=($(docker images --format="{{json .}}" | jq -r 'select((.Tag=="v1.6.1") or (.Tag!="<none>" and .Repository!="aquasec/trivy")) | "\(.Repository):\(.Tag)"'))

echo "CVEs per image:" >> $SCAN_SUMMARY_FILE
echo " IMAGE | BASE | CRITICAL | HIGH | MEDIUM | LOW " >> $SCAN_SUMMARY_FILE
echo " -- | -- | -- | -- | -- | -- " >> $SCAN_SUMMARY_FILE
# for every image generate trivy report and store it in `trivy-reports/` directory
# ':' and '/' in image names are replaced with '-' for files
for IMAGE in "${IMAGE_LIST[@]}"; do
    TRIVY_REPORT="fixed-cve-$DATE-$IMAGE"
    TRIVY_REPORT=$(echo $TRIVY_REPORT | sed 's/:/-/g')
    TRIVY_REPORT=$(echo $TRIVY_REPORT | sed 's/\//-/g')
    TRIVY_REPORT=$(echo "trivy-reports/$TRIVY_REPORT")
    docker run -v /var/run/docker.sock:/var/run/docker.sock -v `pwd`:`pwd` -w `pwd` aquasec/trivy image -f json -o $TRIVY_REPORT.json --ignore-unfixed $IMAGE
    NUM_CRITICAL=$(grep CRITICAL $TRIVY_REPORT.json | wc -l)
    NUM_HIGH=$(grep HIGH $TRIVY_REPORT.json | wc -l)
    NUM_MEDIUM=$(grep MEDIUM $TRIVY_REPORT.json | wc -l)
    NUM_LOW=$(grep LOW $TRIVY_REPORT.json | wc -l)
    BASE=$(cat $TRIVY_REPORT.json | jq '.Metadata.OS | "\(.Family):\(.Name)"' | sed 's/"//g')
    echo " $IMAGE | $BASE | $NUM_CRITICAL | $NUM_HIGH | $NUM_MEDIUM | $NUM_LOW " >> $SCAN_SUMMARY_FILE
done

NUM_CRITICAL=$(grep CRITICAL trivy-reports/* | wc -l)
NUM_HIGH=$(grep HIGH trivy-reports/* | wc -l)
NUM_MEDIUM=$(grep MEDIUM trivy-reports/* | wc -l)
NUM_LOW=$(grep LOW trivy-reports/* | wc -l)
echo "| | Totals: | $NUM_CRITICAL | $NUM_HIGH | $NUM_MEDIUM | $NUM_LOW" >> $SCAN_SUMMARY_FILE
cat $SCAN_SUMMARY_FILE

# End of Kubeflow container images scan
