# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for Jupyter controller."""

import json
import logging
from pathlib import Path

import pytest
import requests
import tenacity
import yaml
from httpx import HTTPStatusError
from lightkube import ApiError, Client
from lightkube.generic_resource import create_namespaced_resource
from lightkube.resources.apiextensions_v1 import CustomResourceDefinition
from lightkube.resources.core_v1 import Namespace, Service
from pytest_operator.plugin import OpsTest

log = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Test build and deploy."""
    await ops_test.model.deploy(
        "istio-pilot",
        channel="latest/edge",
        config={"default-gateway": "test-gateway"},
        trust=True,
    )
    await ops_test.model.deploy(
        "istio-gateway",
        application_name="istio-ingressgateway",
        channel="latest/edge",
        config={"kind": "ingress"},
        trust=True,
    )
    await ops_test.model.add_relation("istio-pilot", "istio-ingressgateway")
    await ops_test.model.wait_for_idle(
        ["istio-pilot", "istio-ingressgateway"],
        raise_on_blocked=False,
        status="active",
        timeout=90 * 10,
    )

    await ops_test.model.deploy("jupyter-ui", trust=True)
    await ops_test.model.add_relation("jupyter-ui", "istio-pilot")

    my_charm = await ops_test.build_charm(".")
    image_path = METADATA["resources"]["oci-image"]["upstream-source"]
    resources = {"oci-image": image_path}
    await ops_test.model.deploy(my_charm, resources=resources, trust=True)
    await ops_test.model.wait_for_idle(
        status="active", raise_on_blocked=False, raise_on_error=False
    )

    assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"


async def test_prometheus_integration(ops_test: OpsTest):
    """Deploy prometheus and required relations, then test the metrics."""
    prometheus = "prometheus-k8s"
    prometheus_scrape = "prometheus-scrape-config-k8s"
    scrape_config = {"scrape_interval": "30s"}

    # Deploy and relate prometheus
    await ops_test.model.deploy(prometheus, channel="latest/stable", trust=True)
    await ops_test.model.deploy(prometheus_scrape, channel="latest/stable", config=scrape_config)

    await ops_test.model.add_relation(APP_NAME, prometheus_scrape)
    await ops_test.model.add_relation(
        f"{prometheus}:metrics-endpoint", f"{prometheus_scrape}:metrics-endpoint"
    )

    await ops_test.model.wait_for_idle(status="active", timeout=60 * 20)

    status = await ops_test.model.get_status()
    prometheus_unit_ip = status["applications"][prometheus]["units"][f"{prometheus}/0"]["address"]
    log.info(f"Prometheus available at http://{prometheus_unit_ip}:9090")

    for attempt in retry_for_5_attempts:
        log.info(f"Testing prometheus deployment (attempt {attempt.retry_state.attempt_number})")
        with attempt:
            r = requests.get(
                f"http://{prometheus_unit_ip}:9090/api/v1/query?"
                f'query=up{{juju_application="{APP_NAME}"}}'
            )
            response = json.loads(r.content.decode("utf-8"))
            response_status = response["status"]
            log.info(f"Response status is {response_status}")
            assert response_status == "success"
            assert len(response["data"]) > 0
            assert len(response["data"]["result"]) > 0
            response_metric = response["data"]["result"][0]["metric"]
            assert response_metric["juju_application"] == APP_NAME
            assert response_metric["juju_model"] == ops_test.model_name

    # Verify that Prometheus receives the same set of targets as specified.
    for attempt in retry_for_5_attempts:
        log.info(f"Testing prometheus targets (attempt {attempt.retry_state.attempt_number})")
        with attempt:
            # obtain scrape targets from Prometheus
            targets_result = requests.get(f"http://{prometheus_unit_ip}:9090/api/v1/targets")
            response = json.loads(targets_result.content.decode("utf-8"))
            response_status = response["status"]
            log.info(f"Response status is {response_status}")
            assert response_status == "success"

            # verify that Argo Controller is in the target list
            discovered_labels = response["data"]["activeTargets"][0]["discoveredLabels"]
            assert discovered_labels["juju_application"] == "jupyter-controller"

    # Verify that Prometheus receives the same set of alert rules as specified.
    for attempt in retry_for_5_attempts:
        log.info(f"Testing prometheus rules (attempt {attempt.retry_state.attempt_number})")
        with attempt:
            # obtain alert rules from Prometheus
            rules_result = requests.get(f"http://{prometheus_unit_ip}:9090/api/v1/rules")
            response = json.loads(rules_result.content.decode("utf-8"))
            response_status = response["status"]
            log.info(f"Response status is {response_status}")
            assert response_status == "success"

            # verify alerts are available in Prometheus
            assert len(response["data"]["groups"]) > 0
            rules = []
            for group in response["data"]["groups"]:
                for rule in group["rules"]:
                    rules.append(rule)

            # load alert rules from rules files
            test_alerts = []
            with open("src/prometheus_alert_rules/controller.rule") as f:
                file_alert = yaml.safe_load(f.read())
                test_alerts.append(file_alert["alert"])
            with open("src/prometheus_alert_rules/host_resources.rules") as f:
                file_alert = yaml.safe_load(f.read())
                # there 2 alert rules in host_resources.rules
                for rule in file_alert["groups"][0]["rules"]:
                    test_alerts.append(rule["alert"])
            with open("src/prometheus_alert_rules/model_errors.rule") as f:
                file_alert = yaml.safe_load(f.read())
                test_alerts.append(file_alert["alert"])
            with open("src/prometheus_alert_rules/unit_unavailable.rule") as f:
                file_alert = yaml.safe_load(f.read())
                test_alerts.append(file_alert["alert"])

            # verify number of alerts is the same in Prometheus and in the rules file
            assert len(rules) == len(test_alerts)

            # verify that all Jupyter Controller alert rules are in the list and that alerts are
            # obtained from Prometheus
            # match alerts in the rules files
            for rule in rules:
                assert rule["name"] in test_alerts


# Helper to retry calling a function over 30 seconds or 5 attempts
retry_for_5_attempts = tenacity.Retrying(
    stop=(tenacity.stop_after_attempt(5) | tenacity.stop_after_delay(30)),
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

    dep = client.get(resource_class, resource_name, namespace=namespace)
    replicas = dep.get("status", {}).get("readyReplicas")

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
