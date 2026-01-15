"""Charms dependencies for tests."""

from charmed_kubeflow_chisme.testing import CharmSpec

JUPYTER_UI = CharmSpec(charm="jupyter-ui", channel="latest/edge", trust=True)
ISTIO_GATEWAY = CharmSpec(
    charm="istio-gateway", channel="latest/edge", trust=True, config={"kind": "ingress"}
)
ISTIO_PILOT = CharmSpec(
    charm="istio-pilot",
    channel="latest/edge",
    trust=True,
    config={"default-gateway": "kubeflow-gateway"},
)
KUBEFLOW_PROFILES = CharmSpec(
    charm="kubeflow-profiles",
    channel="latest/edge",
    trust=True,
    config={
        "service-mesh-mode": "istio-ambient",
        "istio-gateway-principal": "cluster.local/ns/kubeflow/sa/istio-ingress-k8s-istio",
    },
)
