"""Charms dependencies for tests."""

from charmed_kubeflow_chisme.testing import CharmSpec

JUPYTER_UI = CharmSpec(charm="jupyter-ui", channel="1.11/edge", trust=True)
ISTIO_GATEWAY = CharmSpec(
    charm="istio-gateway", channel="1.28/edge", trust=True, config={"kind": "ingress"}
)
ISTIO_PILOT = CharmSpec(
    charm="istio-pilot",
    channel="1.28/edge",
    trust=True,
    config={"default-gateway": "kubeflow-gateway"},
)
KUBEFLOW_PROFILES = CharmSpec(
    charm="kubeflow-profiles",
    channel="2.0/edge",
    trust=True,
    config={
        "service-mesh-mode": "istio-ambient",
        "istio-gateway-service-account": "istio-ingress-k8s-istio",
    },
)
