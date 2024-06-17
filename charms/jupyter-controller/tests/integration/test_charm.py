# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for Jupyter controller."""

import logging
from pathlib import Path

import pytest
import tenacity
import yaml
from charmed_kubeflow_chisme.testing import (
    GRAFANA_AGENT_APP,
    assert_alert_rules,
    assert_logging,
    assert_metrics_endpoint,
    deploy_and_assert_grafana_agent,
    get_alert_rules,
)
from httpx import HTTPStatusError
from lightkube import ApiError, Client
from lightkube.generic_resource import create_namespaced_resource
from lightkube.resources.apiextensions_v1 import CustomResourceDefinition
from lightkube.resources.core_v1 import Namespace, Service
from pytest_operator.plugin import OpsTest

log = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
JUPYTER_UI = "jupyter-ui"
JUPYTER_UI_CHANNEL = "latest/edge"
JUPYTER_UI_TRUST = True

ISTIO_OPERATORS_CHANNEL = "latest/edge"
ISTIO_PILOT = "istio-pilot"
ISTIO_PILOT_TRUST = True
ISTIO_PILOT_CONFIG = {"default-gateway": "kubeflow-gateway"}
ISTIO_GATEWAY = "istio-gateway"
ISTIO_GATEWAY_APP_NAME = "istio-ingressgateway"
ISTIO_GATEWAY_TRUST = True
ISTIO_GATEWAY_CONFIG = {"kind": "ingress"}


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Test build and deploy."""
    # Deploy istio-operators first
    await ops_test.model.deploy(
        entity_url=ISTIO_PILOT,
        channel=ISTIO_OPERATORS_CHANNEL,
        config=ISTIO_PILOT_CONFIG,
        trust=ISTIO_PILOT_TRUST,
    )
    await ops_test.model.deploy(
        entity_url=ISTIO_GATEWAY,
        application_name=ISTIO_GATEWAY_APP_NAME,
        channel=ISTIO_OPERATORS_CHANNEL,
        config=ISTIO_GATEWAY_CONFIG,
        trust=ISTIO_GATEWAY_TRUST,
    )

    await ops_test.model.integrate(ISTIO_PILOT, ISTIO_GATEWAY_APP_NAME)

    await ops_test.model.wait_for_idle(
        status="active",
        raise_on_blocked=False,
        raise_on_error=True,
        timeout=300,
    )
    # Deploy jupyter-ui and relate to istio
    await ops_test.model.deploy(JUPYTER_UI, channel=JUPYTER_UI_CHANNEL, trust=JUPYTER_UI_TRUST)
    await ops_test.model.integrate(JUPYTER_UI, ISTIO_PILOT)
    await ops_test.model.wait_for_idle(apps=[JUPYTER_UI], status="active", timeout=60 * 15)

    my_charm = await ops_test.build_charm(".")
    image_path = METADATA["resources"]["oci-image"]["upstream-source"]
    resources = {"oci-image": image_path}
    await ops_test.model.deploy(my_charm, resources=resources, trust=True)
    await ops_test.model.wait_for_idle(
        status="active", raise_on_blocked=False, raise_on_error=False
    )

    assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"

    # Deploying grafana-agent-k8s and add all relations
    await deploy_and_assert_grafana_agent(
        ops_test.model, APP_NAME, metrics=True, dashboard=True, logging=True
    )


async def test_alert_rules(ops_test):
    """Test check charm alert rules and rules defined in relation data bag."""
    app = ops_test.model.applications[APP_NAME]
    alert_rules = get_alert_rules()
    log.info("found alert_rules: %s", alert_rules)
    await assert_alert_rules(app, alert_rules)


async def test_metrics_enpoint(ops_test):
    """Test metrics_endpoints are defined in relation data bag and their accessibility.

    This function gets all the metrics_endpoints from the relation data bag, checks if
    they are available from the grafana-agent-k8s charm and finally compares them with the
    ones provided to the function.
    """
    app = ops_test.model.applications[APP_NAME]
    await assert_metrics_endpoint(app, metrics_port=8080, metrics_path="/metrics")


async def test_logging(ops_test):
    """Test logging is defined in relation data bag."""
    app = ops_test.model.applications[GRAFANA_AGENT_APP]
    await assert_logging(app)


# Helper to retry calling a function over 30 seconds for 10 attempts
retry_for_5_attempts = tenacity.Retrying(
    stop=(tenacity.stop_after_attempt(10) | tenacity.stop_after_delay(30)),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)


@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=2, min=1, max=10),
    stop=tenacity.stop_after_attempt(30),
    reraise=True,
)
def assert_replicas(client, resource_class, resource_name, namespace):
    """Test for replicas. Retries multiple times to allow for notebook to be created."""

    notebook = client.get(resource_class, resource_name, namespace=namespace)
    replicas = notebook.get("status", {}).get("readyReplicas")

    resource_class_kind = resource_class.__name__
    if replicas == 1:
        log.info(f"{resource_class_kind}/{resource_name} readyReplicas == {replicas}")
    else:
        log.info(
            f"{resource_class_kind}/{resource_name} readyReplicas == {replicas} (waiting for '1')"
        )

    assert replicas == 1, f"Waited too long for {resource_class_kind}/{resource_name}!"


async def test_create_notebook(ops_test: OpsTest):
    """Test notebook creation."""
    lightkube_client = Client()
    this_ns = lightkube_client.get(res=Namespace, name=ops_test.model.name)
    lightkube_client.patch(res=Namespace, name=this_ns.metadata.name, obj=this_ns)

    notebook_resource = create_namespaced_resource(
        group="kubeflow.org",
        version="v1",
        kind="notebook",
        plural="notebooks",
        verbs=None,
    )
    with open("examples/sample-notebook.yaml") as f:
        notebook = notebook_resource(yaml.safe_load(f.read()))
        lightkube_client.create(notebook, namespace=ops_test.model.name)

    try:
        notebook_ready = lightkube_client.get(
            notebook_resource,
            name="sample-notebook",
            namespace=ops_test.model.name,
        )
    except ApiError:
        assert False
    assert notebook_ready

    assert_replicas(lightkube_client, notebook_resource, "sample-notebook", ops_test.model.name)


@pytest.mark.abort_on_fail
async def test_remove_with_resources_present(ops_test: OpsTest):
    """Test remove with all resources deployed.

    Verify that all deployed resources that need to be removed are removed.
    """

    # remove deployed charm and verify that it is removed
    await ops_test.model.remove_application(app_name=APP_NAME, block_until_done=True)
    assert APP_NAME not in ops_test.model.applications

    # verify that all resources that were deployed are removed
    lightkube_client = Client()

    # verify all CRDs in namespace are removed
    crd_list = lightkube_client.list(
        CustomResourceDefinition,
        labels=[("app.juju.is/created-by", "jupyter-controller")],
        namespace=ops_test.model.name,
    )
    assert not list(crd_list)

    # verify that Service is removed
    try:
        _ = lightkube_client.get(
            Service,
            name="jupyter-controller",
            namespace=ops_test.model.name,
        )
    except ApiError as error:
        if error.status.code != 404:
            # other error than Not Found
            assert False

    # verify notebook is deleted
    notebook_resource = create_namespaced_resource(
        group="kubeflow.org",
        version="v1",
        kind="notebook",
        plural="notebooks",
    )
    try:
        _ = lightkube_client.get(
            notebook_resource,
            name="sample-notebook",
            namespace=ops_test.model.name,
        )
    except HTTPStatusError:
        assert True
    except ApiError as error:
        if error.status.code != 404:
            # other error than Not Found
            assert False
