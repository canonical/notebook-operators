# Charmed Jupyter Controller

[![Charmed Jupyter Controller](https://charmhub.io/jupyter-controller/badge.svg)](https://charmhub.io/jupyter-controller)

# Description

Charmed Jupyter Controller is an operator for Kubeflow Jupyter Notebook Controller that allows users to create Jupyter Notebooks.
This charm is part of the Charmed Notebooks Operators bundle which is an integral part of [Charmed Kubeflow](https://charmhub.io/kubeflow).

# Service Mesh

This release supports Istio ambient mesh only. Relate `service-mesh` to
`istio-beacon-k8s` and `gateway-metadata` to `istio-ingress-k8s`. The charm is
blocked if either relation is missing and waits for valid gateway metadata once
related. It no longer falls back to sidecar Istio or a hardcoded gateway.
