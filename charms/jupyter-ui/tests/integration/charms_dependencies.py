"""Charms dependencies for tests."""

from charmed_kubeflow_chisme.testing import CharmSpec

ISTIO_K8S = CharmSpec(
    charm="istio-k8s",
    channel="2/edge",
    trust=True,
)

ISTIO_INGRESS_K8S = CharmSpec(
    charm="istio-ingress-k8s",
    channel="2/edge",
    trust=True,
)

ISTIO_BEACON_K8S = CharmSpec(
    charm="istio-beacon-k8s",
    channel="2/edge",
    trust=True,
)
