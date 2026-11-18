# Charmed Jupyter Notebook Operators

[![Charmed Jupyter Controller](https://charmhub.io/jupyter-controller/badge.svg)](https://charmhub.io/jupyter-controller)
[![Charmed Jupyter UI](https://charmhub.io/jupyter-ui/badge.svg)](https://charmhub.io/jupyter-ui)


# Description

This repository contains the [Jupyter Controller](./charms/jupyter-controller) and
[Jupyter UI](./charms/jupyter-ui) charms, which are part of
[Charmed Kubeflow](https://charmhub.io/kubeflow).

# Running Integration Tests

Integration tests run per charm. See the `integration` job in the
[CI workflow](./.github/workflows/ci.yaml) for runner setup and commands for both
Istio sidecar and ambient modes.

CI deploys packed charms from the same build, including the Jupyter UI dependency
in the controller tests. For local runs, pass `--charm-path` after tox's `--` to
use a prebuilt charm, and pass `--jupyter-ui-charm-path` to supply the UI artifact
to the controller tests. If you omit either path, the tests build the corresponding
charm from the local checkout.
