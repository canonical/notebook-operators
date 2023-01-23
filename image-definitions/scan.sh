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
DATE=$(date +'%Y%-m%d')
echo "Tag: $TAG"
echo "Date: $DATE"

# create directory for trivy reports
mkdir -p trivy-reports

# get all images that are available for scanning
# excluded:
# - tagged with `<none>`
# - aquasec/trivy repository (scanner)
IMAGE_LIST=($(docker images --format="{{json .}}" | jq -r 'select((.Tag=="v1.6.1") or (.Tag!="<none>" and .Repository!="aquasec/trivy")) | "\(.Repository):\(.Tag)"'))

# for every image generate trivy report and store it in `trivy-reports/` directory
# ':' and '/' in image names are replaced with '-' for files
for IMAGE in "${IMAGE_LIST[@]}"; do
    TRIVY_REPORT="fixed-cve-$DATE-$IMAGE"
    TRIVY_REPORT=$(echo $TRIVY_REPORT | sed 's/:/-/g')
    TRIVY_REPORT=$(echo $TRIVY_REPORT | sed 's/\//-/g')
    TRIVY_REPORT=$(echo "trivy-reports/$TRIVY_REPORT")
    docker run -v /var/run/docker.sock:/var/run/docker.sock -v `pwd`:`pwd` -w `pwd` aquasec/trivy image -f json -o $TRIVY_REPORT.json --ignore-unfixed $IMAGE
    # generate CVE record fo KF-CVE (prototype)
    #cat $TRIVY_REPORT | jq '.Results[].Vulnerabilities[]' | jq -r 'select(.Severity=="CRITICAL" or .Severity=="HIGH") | "Source: Trivy scan Component or Image: $IMAGE Library:\(.PkgID) Vulnerability:\(.VulnerabilityID) Severity:\(.Severity) Installed Version:\(.InstalledVersion) Fixed Version:\(.FixedVersion) Title:\(.Title) Description:\(.Description) References:\(.References)"'
done

# End of Kubeflow container images scan
