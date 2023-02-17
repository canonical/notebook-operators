import json
import logging
from pathlib import Path
from random import choices
from string import ascii_lowercase
from time import sleep

import pytest
import requests
import tenacity
import yaml
from lightkube import Client
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import Namespace, Service, ServiceAccount
from selenium.common.exceptions import JavascriptException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC  # noqa: N812
from selenium.webdriver.support.ui import WebDriverWait
from seleniumwire import webdriver

logger = logging.getLogger(__name__)

CONTROLLER_PATH = Path("charms/jupyter-controller")
UI_PATH = Path("charms/jupyter-ui")
CONTROLLER_METADATA = yaml.safe_load(Path(f"{CONTROLLER_PATH}/metadata.yaml").read_text())
UI_METADATA = yaml.safe_load(Path(f"{UI_PATH}/metadata.yaml").read_text())
CONTROLLER_APP_NAME = CONTROLLER_METADATA["name"]
UI_APP_NAME = UI_METADATA["name"]


INGRESSGATEWAY_NAME = "istio-ingressgateway"
PROFILE_NAME = "kubeflow-user"


@pytest.fixture(scope="module")
def lightkube_client(ops_test):
    c = Client()
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
    # FIXME: once tracks for all kubeflow components are released, we should point to
    # those instead of latest/edge
    # Build jupyter-controller and jupyter-ui
    controller_charm = await ops_test.build_charm(CONTROLLER_PATH)
    ui_charm = await ops_test.build_charm(UI_PATH)

    # Gather metadata
    controller_image_path = CONTROLLER_METADATA["resources"]["oci-image"]["upstream-source"]
    ui_image_path = UI_METADATA["resources"]["oci-image"]["upstream-source"]

    # Deploy istio-operators first
    await ops_test.model.deploy(
        "istio-pilot",
        channel="latest/edge",
        config={"default-gateway": "test-gateway"},
        trust=True,
    )
    await ops_test.model.deploy(
        "istio-gateway",
        application_name=INGRESSGATEWAY_NAME,
        channel="latest/edge",
        trust=True,
        config={"kind": "ingress"},
    )
    await ops_test.model.add_relation("istio-pilot", INGRESSGATEWAY_NAME)
    await ops_test.model.wait_for_idle(
        ["istio-pilot", INGRESSGATEWAY_NAME],
        raise_on_blocked=False,
        status="active",
        timeout=90 * 10,
    )

    # Deploy jupyter-ui and relate to istio
    await ops_test.model.deploy(
        ui_charm, resources={"oci-image": ui_image_path}, application_name=UI_APP_NAME, trust=True
    )
    await ops_test.model.add_relation(UI_APP_NAME, "istio-pilot")
    await ops_test.model.wait_for_idle(apps=[UI_APP_NAME], status="active", timeout=60 * 15)

    # Deploy jupyter-controller, admission-webhook, kubeflow-profiles and kubeflow-dashboard
    await ops_test.model.deploy(controller_charm, resources={"oci-image": controller_image_path})
    await ops_test.model.deploy("admission-webhook", channel="latest/edge")
    await ops_test.model.deploy("kubeflow-profiles", channel="latest/edge", trust=True)
    await ops_test.model.deploy("kubeflow-dashboard", channel="latest/edge", trust=True)
    await ops_test.model.add_relation("kubeflow-profiles", "kubeflow-dashboard")

    # Wait for everything to deploy
    await ops_test.model.wait_for_idle(
        status="active",
        raise_on_blocked=True,
        timeout=60 * 20,
    )


@pytest.fixture()
def driver(request, ops_test, lightkube_client):
    this_namespace = ops_test.model_name

    ingress_service = lightkube_client.get(
        res=Service, name=f"{INGRESSGATEWAY_NAME}-workload", namespace=this_namespace
    )
    gateway_ip = ingress_service.status.loadBalancer.ingress[0].ip

    url = f'http://{gateway_ip}.nip.io/jupyter/'
    options = Options()
    options.headless = True
    options.log.level = 'trace'
    max_wait = 200  # seconds

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


# jupyter-ui does not reliably report the correct notebook status
# https://github.com/kubeflow/kubeflow/issues/6056
# def test_notebook(driver, ops_test):
#    """Ensures a notebook can be created and connected to."""
#
#    driver, wait, url = driver
#
#    notebook_name = 'ci-test-' + ''.join(choices(ascii_lowercase, k=10))
#
#   # Click "New Server" button
#    new_button = wait.until(EC.presence_of_element_located((By.ID, "newResource")))
#    new_button.click()
#
#    wait.until(EC.url_to_be(url + 'new'))
#
#    # Enter server name
#    name_input = wait.until(
#        EC.presence_of_element_located((By.CSS_SELECTOR, "input[data-placeholder='Name']"))
#    )
#    name_input.send_keys(notebook_name)
#
#    # Click submit on the form. Sleep for 1 second before clicking the submit button because shiny
#    # animations that ignore click events are simply a must.
#    sleep(1)
#    driver.find_element_by_xpath("//*[contains(text(), 'LAUNCH')]").click()
#    wait.until(EC.url_to_be(url))
#
#    # Since upstream doesn't use proper class names or IDs or anything, find the <tr> containing
#    # elements that contain the notebook name and `ready`, signifying that the notebook is finished
#    # booting up. Returns a reference to the connect button, suitable for clicking on.
#    # The result is a fairly unreadable XPath reference, but it works 🤷
#    chonky_boi = [
#        f"//*[contains(text(), '{notebook_name}')]",
#        "/ancestor::tr",
#        "//*[contains(@class, 'ready')]",
#        "/ancestor::tr",
#        "//*[contains(@class, 'action-button')]",
#        "//button",
#    ]
#    chonky_boi = ''.join(chonky_boi)
#    wait.until(EC.presence_of_element_located((By.XPATH, chonky_boi))).click()
#
#    # Make sure we can connect to a specific notebook's endpoint.
#    # Notebook is opened in a new tab, so we have to explicitly switch to it, run our tests, close
#    # it, then switch back to the main window.
#    driver.switch_to.window(driver.window_handles[-1])
#    expected_path = f'/notebook/kubeflow-user/{notebook_name}/lab'
#    for _ in range(12):
#        path = urlparse(driver.current_url).path
#        if path == expected_path:
#            break
#
#        # Page took a while to load, so can't refresh it too quickly. Sometimes took longer than 5
#        # seconds, never longer than 10 seconds
#        sleep(10)
#        driver.refresh()
#    else:
#        pytest.fail(
#            "Waited too long for selenium to open up notebook server. "
#            f"Expected current path to be `{expected_path}`, got `{path}`."
#        )
#
#    # Wait for main content div to load
#    # TODO: More testing of notebook UIs
#    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "jp-Launcher-sectionTitle")))
#    driver.execute_script('window.close()')
#    driver.switch_to.window(driver.window_handles[-1])
#
#    # Delete notebook, and wait for it to finalize
#    driver.find_element_by_xpath("//*[contains(text(), 'delete')]").click()
#    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "mat-warn"))).click()
#
#    wait.until_not(
#        EC.presence_of_element_located((By.XPATH, f"//*[contains(text(), '{notebook_name}')]"))
#    )


@pytest.mark.skip('Skipping due to this test being inconsistent, and it will be changed soon')
def test_create_notebook(driver, ops_test, dummy_resources_for_testing):
    """Ensures a notebook can be created. Does not test connection due to upstream bug.
    https://github.com/kubeflow/kubeflow/issues/6056
    When the bug is fixed, remove this test and re-enable `test_notebook` test above."""
    driver, wait, url = driver

    notebook_name = 'ci-test-' + ''.join(choices(ascii_lowercase, k=10))

    # Click "New Notebook" button
    wait.until(EC.element_to_be_clickable((By.ID, "newResource"))).click()
    wait.until(EC.url_matches('new'))

    # Enter server name
    name_input = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[data-placeholder='Name']"))
    )
    name_input.click()
    name_input.send_keys(notebook_name)

    # Scrolling would fail without this sleep
    sleep(1)

    # scroll to bottom of the page for launch button
    driver.execute_script("window.scrollTo(0,document.body.scrollHeight)")

    launch_button = wait.until(
        EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'LAUNCH')]"))
    )
    launch_button.click()
    wait.until(EC.url_matches(url))

    # Check the notebook name is displayed
    wait.until(
        EC.presence_of_element_located((By.XPATH, f"//*[contains(text(), '{notebook_name}')]"))
    )


async def test_prometheus_grafana_integration(ops_test):
    """Deploy prometheus, grafana and required relations, then test the metrics."""
    prometheus = "prometheus-k8s"
    grafana = "grafana-k8s"
    prometheus_scrape = "prometheus-scrape-config-k8s"
    scrape_config = {"scrape_interval": "30s"}

    # Deploy and relate prometheus
    await ops_test.model.deploy(prometheus, channel="latest/edge", trust=True)
    await ops_test.model.deploy(grafana, channel="latest/edge", trust=True)
    await ops_test.model.deploy(prometheus_scrape, channel="latest/beta", config=scrape_config)

    await ops_test.model.add_relation(CONTROLLER_APP_NAME, prometheus_scrape)
    await ops_test.model.add_relation(
        f"{prometheus}:grafana-dashboard", f"{grafana}:grafana-dashboard"
    )
    await ops_test.model.add_relation(
        f"{CONTROLLER_APP_NAME}:grafana-dashboard", f"{grafana}:grafana-dashboard"
    )
    await ops_test.model.add_relation(
        f"{prometheus}:metrics-endpoint", f"{prometheus_scrape}:metrics-endpoint"
    )

    await ops_test.model.wait_for_idle(status="active", timeout=60 * 20)

    status = await ops_test.model.get_status()
    prometheus_unit_ip = status["applications"][prometheus]["units"][f"{prometheus}/0"]["address"]
    logger.info(f"Prometheus available at http://{prometheus_unit_ip}:9090")

    for attempt in retry_for_5_attempts:
        logger.info(
            f"Testing prometheus deployment (attempt " f"{attempt.retry_state.attempt_number})"
        )
        with attempt:
            r = requests.get(
                f'http://{prometheus_unit_ip}:9090/api/v1/query?'
                f'query=up{{juju_application="{CONTROLLER_APP_NAME}"}}'
            )
            response = json.loads(r.content.decode("utf-8"))
            response_status = response["status"]
            logger.info(f"Response status is {response_status}")
            assert response_status == "success"

            response_metric = response["data"]["result"][0]["metric"]
            assert response_metric["juju_application"] == CONTROLLER_APP_NAME
            assert response_metric["juju_model"] == ops_test.model_name


# Helper to retry calling a function over 30 seconds or 5 attempts
retry_for_5_attempts = tenacity.Retrying(
    stop=(tenacity.stop_after_attempt(5) | tenacity.stop_after_delay(30)),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
