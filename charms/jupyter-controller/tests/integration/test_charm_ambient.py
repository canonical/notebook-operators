# Copyright 2025 Canonical Ltd.
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
    assert_security_context,
    deploy_and_assert_grafana_agent,
    deploy_and_integrate_service_mesh_charms,
    generate_container_securitycontext_map,
    get_alert_rules,
    get_pod_names,
    integrate_with_service_mesh,
)
from charms_dependencies import JUPYTER_UI
from httpx import HTTPStatusError
from lightkube import ApiError, Client
from lightkube.generic_resource import create_namespaced_resource
from lightkube.resources.apiextensions_v1 import CustomResourceDefinition
from lightkube.resources.core_v1 import Namespace, Service
from pytest_operator.plugin import OpsTest

log = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
CONTAINERS_SECURITY_CONTEXT_MAP = generate_container_securitycontext_map(METADATA)

HTTP_ROUTE = create_namespaced_resource(
    group="gateway.networking.k8s.io",
    version="v1",
    kind="HTTPRoute",
    plural="httproutes",
)

NOTEBOOK_RESOURCE = create_namespaced_resource(
    group="kubeflow.org",
    version="v1",
    kind="notebook",
    plural="notebooks",
    verbs=None,
)


@pytest.fixture(scope="session")
def lightkube_client() -> Client:
    """Returns lightkube Kubernetes client"""
    client = Client(field_manager=f"{APP_NAME}")
    return client


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, request):
    """Test build and deploy."""

    # Deploy jupyter-ui
    await ops_test.model.deploy(
        JUPYTER_UI.charm, channel=JUPYTER_UI.channel, trust=JUPYTER_UI.trust
    )

    # Keep the option to run the integration tests locally
    # by building the charm and then deploying
    entity_url = (
        await ops_test.build_charm("./")
        if not (entity_url := request.config.getoption("--charm-path"))
        else entity_url
    )
    image_path = METADATA["resources"]["oci-image"]["upstream-source"]
    resources = {"oci-image": image_path}
    await ops_test.model.deploy(entity_url, resources=resources, trust=True)
    await ops_test.model.wait_for_idle(
        status="active", raise_on_blocked=False, raise_on_error=False
    )

    assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"

    # Deploy Istio service mesh charms and integrate with Jupyter Controller
    await deploy_and_integrate_service_mesh_charms(
        app=APP_NAME,
        model=ops_test.model,
        relate_to_ingress=False,
    )

    # Integrate Jupyter UI with service mesh
    await integrate_with_service_mesh(
        app=JUPYTER_UI.charm,
        model=ops_test.model,
    )

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


async def test_create_notebook(ops_test: OpsTest, lightkube_client: Client):
    """Test notebook creation."""
    this_ns = lightkube_client.get(res=Namespace, name=ops_test.model.name)
    lightkube_client.patch(res=Namespace, name=this_ns.metadata.name, obj=this_ns)

    with open("examples/sample-notebook.yaml") as f:
        notebook = NOTEBOOK_RESOURCE(yaml.safe_load(f.read()))
        lightkube_client.create(notebook, namespace=ops_test.model.name)

    try:
        notebook_ready = lightkube_client.get(
            NOTEBOOK_RESOURCE,
            name="sample-notebook",
            namespace=ops_test.model.name,
        )
    except ApiError:
        assert False
    assert notebook_ready

    assert_replicas(lightkube_client, NOTEBOOK_RESOURCE, "sample-notebook", ops_test.model.name)


async def test_notebook_http_route_created_reachable(ops_test: OpsTest, lightkube_client: Client):
    """Test HTTP route is created for the notebook and is reachable.

    This test reuses the notebook created in test_create_notebook.
    Checks that:
    1. The HTTP route is created by the controller for the notebook.
    2. The Notebook route is reachable through the ingress.
    """
    # TODO: write test logic


@pytest.mark.parametrize("container_name", list(CONTAINERS_SECURITY_CONTEXT_MAP.keys()))
@pytest.mark.abort_on_fail
async def test_container_security_context(
    ops_test: OpsTest,
    lightkube_client: Client,
    container_name: str,
):
    """Test container security context is correctly set.

    Verify that container spec defines the security context with correct
    user ID and group ID.
    """
    pod_name = get_pod_names(ops_test.model.name, APP_NAME)[0]
    assert_security_context(
        lightkube_client,
        pod_name,
        container_name,
        CONTAINERS_SECURITY_CONTEXT_MAP,
        ops_test.model.name,
    )


@pytest.mark.skip()
@pytest.mark.abort_on_fail
async def test_remove_with_resources_present(ops_test: OpsTest, lightkube_client: Client):
    """Test remove with all resources deployed.

    Verify that all deployed resources that need to be removed are removed.
    """

    # remove deployed charm and verify that it is removed
    await ops_test.model.remove_application(app_name=APP_NAME, block_until_done=True)
    assert APP_NAME not in ops_test.model.applications

    # verify that all resources that were deployed are removed

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
    try:
        _ = lightkube_client.get(
            NOTEBOOK_RESOURCE,
            name="sample-notebook",
            namespace=ops_test.model.name,
        )
    except HTTPStatusError:
        assert True
    except ApiError as error:
        if error.status.code != 404:
            # other error than Not Found
            assert False
