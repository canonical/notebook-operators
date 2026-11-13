# Charmed Jupyter Notebook Operators

[![Charmed Jupyter](https://charmhub.io/jupyter/badge.svg)](https://charmhub.io/jupyter)


# Description

This bundle contains Charmed Operators for Kubeflow Jupyter Notebook Controller and Kubeflow Jupyter UI web application (see [CharmHub](https://charmhub.io/?q=jupyter)).

# Install

The notebook operators require Istio ambient mesh. The bundle deploys `istio-k8s`,
`istio-ingress-k8s`, and `istio-beacon-k8s` alongside the notebook operators and
their Kubeflow dependencies. Deploy it into a prepared Kubernetes Juju model:

    juju deploy ./bundle.yaml --trust

The controller is blocked without `service-mesh` or `gateway-metadata`; once
related, it waits for gateway metadata relation data. The UI is blocked without
`service-mesh` or `istio-ingress-route`. The UI supports multiple
ambient ingress relations.

For more information, see https://juju.is/docs

# Running Integration Tests

The integration suites exercise deployment and operation with Istio ambient mesh.
With Kubernetes and a
Juju controller prepared, run each suite in a clean model:

```bash
tox -e jupyter-controller-integration
tox -e jupyter-ui-integration
```

See [.github/workflows/ci.yaml](.github/workflows/ci.yaml) for CI setup.
