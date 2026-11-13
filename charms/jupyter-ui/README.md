# Charmed Jupyter UI

[![Charmed Jupyter UI](https://charmhub.io/jupyter-ui/badge.svg)](https://charmhub.io/jupyter-ui)

# Description

Charmed Jupyter UI is an operator for Kubeflow Jupyter UI web application that provides users with web UI to access and manipulate Jupyter Notebooks in Charmed Kubeflow.
This charm is part of the Charmed Notebooks Operators bundle which is an integral part of [Charmed Kubeflow](https://charmhub.io/kubeflow).

# Service Mesh

This release supports Istio ambient mesh only. Relate `service-mesh` to
`istio-beacon-k8s` and `istio-ingress-route` to `istio-ingress-k8s`. The charm is
blocked if either relation is missing and supports multiple ambient ingress
relations.

The legacy `ingress` endpoint has been removed. Remove its relations before
refreshing from a sidecar-based deployment, and use `istio-ingress-route` instead.
