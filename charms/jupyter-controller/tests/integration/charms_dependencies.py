"""Charms dependencies for tests."""

from pathlib import Path
from zipfile import ZipFile

<<<<<<< HEAD
JUPYTER_UI = CharmSpec(charm="jupyter-ui", channel="1.11/edge", trust=True)
ISTIO_GATEWAY = CharmSpec(
    charm="istio-gateway", channel="1.28/edge", trust=True, config={"kind": "ingress"}
)
ISTIO_PILOT = CharmSpec(
    charm="istio-pilot",
    channel="1.28/edge",
=======
import yaml
from charmed_kubeflow_chisme.testing import CharmSpec
from pytest_operator.plugin import OpsTest

JUPYTER_UI_APP_NAME = "jupyter-ui"
ISTIO_GATEWAY = CharmSpec(
    charm="istio-gateway", channel="latest/edge", trust=True, config={"kind": "ingress"}
)
ISTIO_PILOT = CharmSpec(
    charm="istio-pilot",
    channel="latest/edge",
>>>>>>> 3ee4d2a (fix: keep istio sidecar support  (#652))
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


async def deploy_jupyter_ui(ops_test: OpsTest, charm_path: str | None) -> None:
    """Deploy the packed UI charm, building it from the sibling checkout if needed."""
    if charm_path is None:
        ui_source = Path(__file__).resolve().parents[3] / JUPYTER_UI_APP_NAME
        artifact = await ops_test.build_charm(ui_source)
    else:
        artifact = Path(charm_path).resolve()

    with ZipFile(artifact) as charm:
        metadata = yaml.safe_load(charm.read("metadata.yaml"))
    await ops_test.model.deploy(
        str(artifact),
        application_name=JUPYTER_UI_APP_NAME,
        resources={"oci-image": metadata["resources"]["oci-image"]["upstream-source"]},
        trust=True,
    )
