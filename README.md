# Charmed Jupyter Notebook Operators

[![Charmed Jupyter Controller](https://charmhub.io/jupyter-controller/badge.svg)](https://charmhub.io/jupyter-controller)
[![Charmed Jupyter UI](https://charmhub.io/jupyter-ui/badge.svg)](https://charmhub.io/jupyter-ui)


# Description

This repository contains the [Jupyter Controller](./charms/jupyter-controller) and
[Jupyter UI](./charms/jupyter-ui) charms, which are part of
[Charmed Kubeflow](https://charmhub.io/kubeflow).

# Install

<<<<<<< HEAD
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
=======
Integration tests run per charm. See the `integration` job in the
[CI workflow](./.github/workflows/ci.yaml) for runner setup and commands for both
Istio sidecar and ambient modes.

CI deploys packed charms from the same build, including the Jupyter UI dependency
in the controller tests. For local runs, pass `--charm-path` after tox's `--` to
use a prebuilt charm, and pass `--jupyter-ui-charm-path` to supply the UI artifact
to the controller tests. If you omit either path, the tests build the corresponding
charm from the local checkout.
>>>>>>> 3ee4d2a (fix: keep istio sidecar support  (#652))
