## Jupyter Notebook Operators

### Overview
This bundle encompasses the Kubernetes Python operators (a.k.a. charms) for Jupyter
(see [CharmHub](https://charmhub.io/?q=jupyter)).

The Jupyter Notebook operators are Python scripts that wrap the latest released [Jupyter Notebook manifests][manifests],
providing lifecycle management for each application, handling events (install, upgrade, integrate, remove).

[manifests]: https://github.com/kubeflow/manifests/tree/master/apps/jupyter


## Install

This Jupyter bundle requires some other components of Kubeflow to be deployed,
including istio and the kubeflow dashboard. It also currently requires some 
manual configuration of the Kubernetes cluster. As these requirements are
subject to change at this time, the most reliable set-up instuctions are 
contained in the `Deploy charm dependencies` section of the
[integration workflow][integrate].

Once those dependencies have been satisfied, you can deploy this Jupyter bundle
with:

    juju deploy jupyter

For more information, see https://juju.is/docs

[integrate]: .github/workflows/integrate.yaml


## Running the Tests

To run tests for this repo:

1. Install non-python test prerequisites
```bash
sudo apt install -y firefox-geckodriver
sudo snap install juju-bundle --classic
sudo snap install juju-wait --classic

```
2. Execute tests in the `kubeflow` model:
```bash
tox -e integration -- --model kubeflow
```
