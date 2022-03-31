import logging
import os
from pathlib import Path
from random import choices
from string import ascii_lowercase
from time import sleep
from urllib.parse import urlparse

import pytest
import yaml
import json
import requests

from lightkube import Client
from lightkube.resources.rbac_authorization_v1 import Role
from lightkube.models.rbac_v1 import PolicyRule
from lightkube.resources.core_v1 import Namespace, ServiceAccount, Service
from lightkube.models.meta_v1 import ObjectMeta
from selenium.common.exceptions import JavascriptException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumwire import webdriver

CONTROLLER_METADATA = yaml.safe_load(Path("charms/jupyter-controller/metadata.yaml").read_text())
UI_METADATA = yaml.safe_load(Path("charms/jupyter-ui/metadata.yaml").read_text())


INGRESSGATEWAY_NAME = "istio-ingressgateway-operator"


@pytest.fixture(scope="module")
def lightkube_client(ops_test):
    # TODO: Not sure why, but `.get(... namespace=somenamespace)` for the istio role patching
    #  would not respect the namespace arg, and instead used the Client's default namespace.  Bug?
    #  remove this when patching is no longer necessary
    this_namespace = ops_test.model_name

    c = Client(namespace=this_namespace)
    yield c


@pytest.fixture(scope="module")
def dummy_resources_for_testing(lightkube_client):
    # Add namespace and service account for testing
    # This namespace is required to test the notebook in standalone mode, but not if accessed
    # through the dashboard
    # The namespace and serviceaccount could be replaced by adding a single Profile named
    # kubeflow-user
    namespace_name = "kubeflow-user"
    namespace_metadata = ObjectMeta(name=namespace_name)
    namespace = Namespace(metadata=namespace_metadata)
    lightkube_client.create(namespace, namespace_name)

    serviceaccount_name = "default-editor"
    serviceaccount_metadata = ObjectMeta(name=serviceaccount_name, namespace=namespace_name)
    serviceaccount = ServiceAccount(metadata=serviceaccount_metadata)
    lightkube_client.create(serviceaccount, serviceaccount_name, namespace=namespace_name)

    yield

    # Clean up dummy resources
    lightkube_client.delete(Namespace, namespace_name)
    lightkube_client.delete(ServiceAccount, serviceaccount_name, namespace=namespace_name)


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test, lightkube_client, dummy_resources_for_testing):
    await ops_test.deploy_bundle(destructive_mode=True, serial=True, extra_args=["--trust"])

    await patch_ingress_gateway(lightkube_client, ops_test)

    # Wait for everything to deploy
    await ops_test.model.wait_for_idle(
        status="active",
        raise_on_blocked=True,
        timeout=360,
    )


async def patch_ingress_gateway(lightkube_client, ops_test):
    """Patch the ingress gateway's roles, allowing configmap access, to fix a bug.

    This can be removed once updating to the istio > 1.5 charm
    """
    # Wait for gateway to come up (and thus create the role we want to patch)
    await ops_test.model.wait_for_idle(
        apps=[INGRESSGATEWAY_NAME],
        status="waiting",
        timeout=300,
    )
    # Patch the role
    this_namespace = ops_test.model_name
    ingressgateway_role_name = f"{INGRESSGATEWAY_NAME}-operator"
    logging.error(f"Looking for role {ingressgateway_role_name} in namespace {this_namespace}")
    new_policy_rule = PolicyRule(verbs=["get", "list"], apiGroups=[""], resources=["configmaps"])
    this_role = lightkube_client.get(Role, ingressgateway_role_name, namespace=this_namespace)
    this_role.rules.append(new_policy_rule)
    lightkube_client.patch(Role, ingressgateway_role_name, this_role)

    # Give a few moments of quick updates to get the gateway to notice the fixed role, but don't
    # leave it this way or the model will never look idle to `wait_for_idle()`
    await ops_test.model.set_config({"update-status-hook-interval": "10s"})
    sleep(60)
    await ops_test.model.set_config({"update-status-hook-interval": "60s"})


@pytest.fixture()
def driver(request, ops_test, lightkube_client):
    this_namespace = ops_test.model_name

    ingress_service = lightkube_client.get(
        res=Service, name=INGRESSGATEWAY_NAME, namespace=this_namespace
    )
    gateway_ip = ingress_service.status.loadBalancer.ingress[0].ip

    url = f'http://{gateway_ip}.nip.io/jupyter/'
    options = Options()
    options.headless = True
    options.log.level = 'trace'
    max_wait = 150  # seconds

    kwargs = {
        'options': options,
        'seleniumwire_options': {'enable_har': True},
    }

    with webdriver.Firefox(**kwargs) as driver:
        wait = WebDriverWait(driver, max_wait, 1, (JavascriptException, StopIteration))
        for _ in range(60):
            try:
                driver.get(url)
                wait.until(EC.presence_of_element_located((By.ID, "newResource")))
                break
            except WebDriverException:
                sleep(5)
        else:
            driver.get(url)

        yield driver, wait, url

        Path(f'/tmp/selenium-{request.node.name}.har').write_text(driver.har)
        driver.get_screenshot_as_file(f'/tmp/selenium-{request.node.name}.png')


def test_notebook(driver, ops_test, dummy_resources_for_testing):
    """Ensures a notebook can be created and connected to."""

    driver, wait, url = driver

    notebook_name = 'ci-test-' + ''.join(choices(ascii_lowercase, k=10))

    # Click "New Server" button
    new_button = wait.until(EC.presence_of_element_located((By.ID, "newResource")))
    new_button.click()

    wait.until(EC.url_to_be(url + 'new'))

    # Enter server name
    name_input = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[data-placeholder='Name']"))
    )
    name_input.send_keys(notebook_name)

    # Click submit on the form. Sleep for 1 second before clicking the submit button because shiny
    # animations that ignore click events are simply a must.
    sleep(1)
    driver.find_element_by_xpath("//*[contains(text(), 'LAUNCH')]").click()
    wait.until(EC.url_to_be(url))

    # Since upstream doesn't use proper class names or IDs or anything, find the <tr> containing
    # elements that contain the notebook name and `ready`, signifying that the notebook is finished
    # booting up. Returns a reference to the connect button, suitable for clicking on. The result is
    # a fairly unreadable XPath reference, but it works 🤷
    chonky_boi = [
        f"//*[contains(text(), '{notebook_name}')]",
        "/ancestor::tr",
        "//*[contains(@class, 'ready')]",
        "/ancestor::tr",
        "//*[contains(@class, 'action-button')]",
        "//button",
    ]
    chonky_boi = ''.join(chonky_boi)
    wait.until(EC.presence_of_element_located((By.XPATH, chonky_boi))).click()

    # Make sure we can connect to a specific notebook's endpoint.
    # Notebook is opened in a new tab, so we have to explicitly switch to it, run our tests, close
    # it, then switch back to the main window.
    driver.switch_to.window(driver.window_handles[-1])
    expected_path = f'/notebook/kubeflow-user/{notebook_name}/lab'
    for _ in range(12):
        path = urlparse(driver.current_url).path
        if path == expected_path:
            break

        # Page took a while to load, so can't refresh it too quickly. Sometimes took longer than 5
        # seconds, never longer than 10 seconds
        sleep(10)
        driver.refresh()
    else:
        pytest.fail(
            "Waited too long for selenium to open up notebook server. "
            f"Expected current path to be `{expected_path}`, got `{path}`."
        )

    # Wait for main content div to load
    # TODO: More testing of notebook UIs
    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "jp-Launcher-sectionTitle")))
    driver.execute_script('window.close()')
    driver.switch_to.window(driver.window_handles[-1])

    # Delete notebook, and wait for it to finalize
    driver.find_element_by_xpath("//*[contains(text(), 'delete')]").click()
    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "mat-warn"))).click()

    wait.until_not(
        EC.presence_of_element_located((By.XPATH, f"//*[contains(text(), '{notebook_name}')]"))
    )


async def test_integrate_with_prometheus_and_grafana(ops_test):
    prometheus = "prometheus-k8s"
    grafana = "grafana-k8s"
    prometheus_scrape = "prometheus-scrape-config-k8s"
    jupyter_controller = "jupyter-controller"
    scrape_config = {"scrape_interval": "30s"}
    await ops_test.model.deploy(prometheus, channel="latest/beta")
    await ops_test.model.deploy(grafana, channel="latest/beta")
    await ops_test.model.deploy(prometheus_scrape, channel="latest/beta", config=scrape_config)
    await ops_test.model.add_relation(jupyter_controller, prometheus_scrape)
    await ops_test.model.add_relation(prometheus, prometheus_scrape)
    await ops_test.model.add_relation(prometheus, grafana)
    await ops_test.model.add_relation(jupyter_controller, grafana)

    await ops_test.model.wait_for_idle([jupyter_controller, prometheus, grafana], status="active")
    status = await ops_test.model.get_status()
    prometheus_unit_ip = status["applications"][prometheus]["units"][f"{prometheus}/0"]["address"]

    r = requests.get(
        f'http://{prometheus_unit_ip}:9090/api/v1/query?query=up{{juju_application="jupyter-controller"}}'
    )
    response = json.loads(r.content.decode("utf-8"))
    assert response["status"] == "success"
    assert len(response["data"]["result"]) == len(
        ops_test.model.applications[jupyter_controller].units
    )

    response_metric = response["data"]["result"][0]["metric"]
    assert response_metric["juju_application"] == jupyter_controller
    assert response_metric["juju_charm"] == jupyter_controller
    assert response_metric["juju_model"] == ops_test.model_name
    assert response_metric["juju_unit"] == f"{jupyter_controller}/0"
