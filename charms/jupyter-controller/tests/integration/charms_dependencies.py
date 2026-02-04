"""Charms dependencies for tests."""

from charmed_kubeflow_chisme.testing import CharmSpec

JUPYTER_UI = CharmSpec(charm="jupyter-ui", channel="1.10/stable", trust=True)
ISTIO_GATEWAY = CharmSpec(
    charm="istio-gateway", channel="1.24/stable", trust=True, config={"kind": "ingress"}
)
ISTIO_PILOT = CharmSpec(
    charm="istio-pilot",
    channel="1.24/stable",
    trust=True,
    config={"default-gateway": "kubeflow-gateway"},
)
