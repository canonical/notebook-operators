# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Integration tests for Jupyter UI Operator/Charm."""

import json
import logging
from pathlib import Path

import dpath
import lightkube
import pytest
import tenacity
import yaml
from charmed_kubeflow_chisme.testing import (
    GRAFANA_AGENT_APP,
    ISTIO_INGRESS_K8S_APP,
    ISTIO_INGRESS_ROUTE_ENDPOINT,
    assert_logging,
    assert_path_reachable_through_ingress,
    deploy_and_assert_grafana_agent,
    deploy_and_integrate_service_mesh_charms,
    get_http_response,
)
from lightkube.generic_resource import create_namespaced_resource
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
CONFIG = yaml.safe_load(Path("./config.yaml").read_text())
APP_NAME = "jupyter-ui"
JUPYTER_IMAGES_CONFIG = "jupyter-images"
VSCODE_IMAGES_CONFIG = "vscode-images"
RSTUDIO_IMAGES_CONFIG = "rstudio-images"
PORT = CONFIG["options"]["port"]["default"]
HEADERS = {
    "kubeflow-userid": "",
}
HTTP_PATH = "/jupyter/"
EXPECTED_RESPONSE_TEXT = "Jupyter Management UI"
# A second istio-ingress-k8s instance used to verify multiple-ingress support.
SECOND_INGRESS_APP = "istio-ingress-k8s-alt"
INGRESS_CHANNEL = "2/stable"
# Name of the HTTPRoute submitted by jupyter-ui (see charm._configure_ambient_ingress).
INGRESS_ROUTE_NAME = "http-route"
# Gateway listener section for cleartext HTTP on port 80.
HTTP_SECTION_NAME = "http-80"
# Gateway API generic resources, resolved at runtime via lightkube.
HTTPROUTE_RESOURCE = create_namespaced_resource(
    "gateway.networking.k8s.io", "v1", "HTTPRoute", "httproutes"
)
GATEWAY_RESOURCE = create_namespaced_resource(
    "gateway.networking.k8s.io", "v1", "Gateway", "gateways"
)
RETRY_120_SECONDS = tenacity.Retrying(
    stop=tenacity.stop_after_delay(120),
    wait=tenacity.wait_fixed(2),
    reraise=True,
)
AFFINITY_OPTIONS = [
    {
        "configKey": "test-affinity-config-1",
        "displayName": "Test Affinity Config-1",
        "affinity": dict(
            nodeAffinity=dict(
                requiredDuringSchedulingIgnoredDuringExecution=[
                    dict(
                        matchExpressions=[
                            dict(key="lifecycle", operator="In", values=["kubeflow-notebook-1"])
                        ]
                    )
                ]
            )
        ),
    },
]

TOLERATIONS_OPTIONS = [
    {
        "groupKey": "test-tolerations-group-1",
        "displayName": "Test Tolerations Group 1",
        "tolerations": [
            dict(effect="NoSchedule", key="dedicated", operator="Equal", value="big-machine")
        ],
    },
]
DEFAULT_PODDEFAULTS = [
    "poddefault1",
    "poddefault2",
]


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, request):
    """Build and deploy the charm.

    Assert on the unit status.
    """
    # Keep the option to run the integration tests locally
    # by building the charm and then deploying
    entity_url = (
        await ops_test.build_charm("./")
        if not (entity_url := request.config.getoption("--charm-path"))
        else entity_url
    )
    image_path = METADATA["resources"]["oci-image"]["upstream-source"]
    resources = {"oci-image": image_path}

    await ops_test.model.deploy(
        entity_url, resources=resources, application_name=APP_NAME, trust=True
    )

    # NOTE: idle_period is used to ensure all resources are deployed
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", raise_on_blocked=True, timeout=60 * 10, idle_period=30
    )
    assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"

    # Deploying grafana-agent-k8s and add all relations
    await deploy_and_assert_grafana_agent(
        ops_test.model, APP_NAME, metrics=False, dashboard=False, logging=True
    )


@pytest.mark.abort_on_fail
async def test_deploy_and_relate_dependencies(ops_test: OpsTest):
    """Deploy and integrate Istio dependencies with the application under test."""
    await deploy_and_integrate_service_mesh_charms(
        app=APP_NAME,
        model=ops_test.model,
    )


@pytest.mark.abort_on_fail
async def test_ui_is_accessible(ops_test: OpsTest):
    """Verify that UI is accessible through the ingress gateway."""
    await assert_path_reachable_through_ingress(
        http_path=HTTP_PATH,
        namespace=ops_test.model_name,
        headers=HEADERS,
        expected_status=200,
        expected_content_type="text/html",
        expected_response_text=EXPECTED_RESPONSE_TEXT,
    )


@pytest.mark.abort_on_fail
async def test_deploy_and_relate_second_ingress(ops_test: OpsTest):
    """Deploy a second istio-ingress-k8s and relate it to jupyter-ui.

    jupyter-ui must accept more than one istio-ingress-route relation without erroring,
    so it should remain active after the second ingress is related.
    """
    await ops_test.model.deploy(
        ISTIO_INGRESS_K8S_APP,
        application_name=SECOND_INGRESS_APP,
        channel=INGRESS_CHANNEL,
        trust=True,
    )
    await ops_test.model.wait_for_idle(
        [SECOND_INGRESS_APP],
        raise_on_blocked=False,
        raise_on_error=False,
        wait_for_active=True,
        timeout=60 * 15,
    )

    await ops_test.model.integrate(
        f"{SECOND_INGRESS_APP}:{ISTIO_INGRESS_ROUTE_ENDPOINT}",
        f"{APP_NAME}:{ISTIO_INGRESS_ROUTE_ENDPOINT}",
    )
    await ops_test.model.wait_for_idle(
        [APP_NAME, SECOND_INGRESS_APP],
        status="active",
        raise_on_blocked=False,
        raise_on_error=False,
        timeout=60 * 10,
        idle_period=30,
    )

    assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"


async def test_httproute_attached_to_second_gateway(ops_test: OpsTest):
    """Verify the HTTPRoute for the second ingress is created and bound to its Gateway.

    The istio-ingress-k8s charm names each route
    ``{source_app}-{route_name}-httproute-{section}-{ingress_app}`` and binds it to a
    Gateway named after the ingress application via ``parentRefs``. We assert that the
    route created for the second ingress is attached to the *second* Gateway (not the
    first) and routes the jupyter-ui path to the jupyter-ui backend.
    """
    namespace = ops_test.model_name
    client = lightkube.Client()

    expected_route_name = (
        f"{APP_NAME}-{INGRESS_ROUTE_NAME}-httproute-{HTTP_SECTION_NAME}-{SECOND_INGRESS_APP}"
    )

    # The second Gateway should exist, named after the second ingress application.
    client.get(GATEWAY_RESOURCE, name=SECOND_INGRESS_APP, namespace=namespace)

    # Retry to give the ingress charm time to reconcile the HTTPRoute resources.
    httproute = None
    for attempt in RETRY_120_SECONDS:
        with attempt:
            httproute = client.get(
                HTTPROUTE_RESOURCE, name=expected_route_name, namespace=namespace
            )

    parent_refs = httproute.spec["parentRefs"]
    assert len(parent_refs) == 1
    # The route must be attached to the SECOND gateway, not the first.
    assert parent_refs[0]["name"] == SECOND_INGRESS_APP
    assert parent_refs[0]["sectionName"] == HTTP_SECTION_NAME

    # And it must route the jupyter-ui path to the jupyter-ui backend.
    rule = httproute.spec["rules"][0]
    assert rule["matches"][0]["path"]["value"] == HTTP_PATH
    assert rule["backendRefs"][0]["name"] == APP_NAME


async def get_unit_address(ops_test: OpsTest):
    """Return the unit address of jupyter-ui application."""
    status = await ops_test.model.get_status()
    jupyter_ui_units = status["applications"]["jupyter-ui"]["units"]
    jupyter_ui_url = jupyter_ui_units["jupyter-ui/0"]["address"]
    return jupyter_ui_url


@pytest.mark.parametrize(
    "config_key,config_value,yaml_path",
    [
        ("jupyter-images", ["jupyterimage1", "jupyterimagse2"], "config/image/options"),
        ("vscode-images", ["vscodeimage1", "vscodeimagse2"], "config/imageGroupOne/options"),
        ("rstudio-images", ["rstudioimage1", "rstudioismage2"], "config/imageGroupTwo/options"),
        ("affinity-options", AFFINITY_OPTIONS, "config/affinityConfig/options"),
        ("gpu-vendors", [{"limitsKey": "gpu1", "uiName": "GPsU 1"}], "config/gpus/value/vendors"),
        ("tolerations-options", TOLERATIONS_OPTIONS, "config/tolerationGroup/options"),
        ("default-poddefaults", DEFAULT_PODDEFAULTS, "config/configurations/value"),
    ],
)
async def test_notebook_configuration(ops_test: OpsTest, config_key, config_value, yaml_path):
    """Test updating notebook configuration settings.

    Verify that setting the juju config for the default notebook configuration settings sets the
    values in the Jupyter UI web form.

    Args:
        config_key: The key in the charm config to set
        config_value: The value to set the config key to
        yaml_path: The path in the spawner_ui_config.yaml file that this config will be rendered to,
                   written as a "/" separated string (e.g. "config/image/options").  See dpath.get()
                   at https://github.com/dpath-maintainers/dpath-python?tab=readme-ov-file#searching
                   for more information on the path syntax.
    """
    await ops_test.model.applications[APP_NAME].set_config({config_key: yaml.dump(config_value)})
    expected_config = config_value

    # To avoid waiting for a long idle_period between each of this series of tests, we do not use
    # wait_for_idle.  Instead we push the config and then try for 120 seconds to assert the config
    # is updated.  This ends up being faster than waiting for idle_period between each test.

    jupyter_ui_url = await get_unit_address(ops_test)
    logger.info("Polling the Jupyter UI API to check the configuration")
    for attempt in RETRY_120_SECONDS:
        logger.info("Testing whether the config has been updated")
        with attempt:
            try:
                _, response_text, _ = await get_http_response(
                    f"http://{jupyter_ui_url}:{PORT}/api/config", HEADERS
                )
                response_json = json.loads(response_text)
                actual_config = dpath.get(response_json, yaml_path)
                assert actual_config == expected_config
            except AssertionError as e:
                logger.info("Failed assertion that config is updated - will retry")
                raise e


async def test_logging(ops_test):
    """Test logging is defined in relation data bag."""
    app = ops_test.model.applications[GRAFANA_AGENT_APP]
    await assert_logging(app)
