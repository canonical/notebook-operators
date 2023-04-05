# Charmed Jupyter Notebook Operators

[![Charmed Jupyter](https://charmhub.io/jupyter/badge.svg)](https://charmhub.io/jupyter)


# Description

This bundle contains Charmed Operators for Kubeflow Jupyter Notebook Controller and Kubeflow Jupyter UI web application (see [CharmHub](https://charmhub.io/?q=jupyter)).

# Install

This Jupyter bundle requires some other components of Kubeflow to be deployed,
including istio and the kubeflow dashboard. It also currently requires some 
manual configuration of the Kubernetes cluster. As these requirements are
subject to change at this time, the most reliable set-up instructions are 
contained in the `Deploy charm dependencies` section of the
[integration workflow][integrate].

Once those dependencies have been satisfied, you can deploy this Jupyter bundle
with:

    juju deploy jupyter

For more information, see https://juju.is/docs

[integrate]: .github/workflows/integrate.yaml


# Running Bundle Tests

The following instructions assume K8S cluster is configured and Juju controller
is bootstraped.

1. Install test prerequisites

NOTE: Refer to `bundle-integration` section of [integration workflow][integrate]
for up-to-date prerequisites installation steps.

```bash
sudo apt install -y firefox-geckodriver

```

2. Execute tests in the `kubeflow` model:

Add `kubeflow` model and execute tests:
```bash
juju add-model kubeflow
tox -e integration -- --model kubeflow
```
