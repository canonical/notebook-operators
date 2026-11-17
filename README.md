# Charmed Jupyter Notebook Operators

[![Charmed Jupyter](https://charmhub.io/jupyter/badge.svg)](https://charmhub.io/jupyter)


# Description

This bundle contains Charmed Operators for Kubeflow Jupyter Notebook Controller and Kubeflow Jupyter UI web application (see [CharmHub](https://charmhub.io/?q=jupyter)).

# Running Integration Tests

The integration suites exercise deployment and operation with Istio ambient mesh.
With Kubernetes and a
Juju controller prepared, run each suite in a clean model:

```bash
tox -e jupyter-controller-integration
tox -e jupyter-ui-integration
```

See [.github/workflows/ci.yaml](.github/workflows/ci.yaml) for CI setup.
