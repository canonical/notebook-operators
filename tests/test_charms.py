import os
from pathlib import Path
from random import choices
from string import ascii_lowercase
from subprocess import check_call, check_output
from time import sleep
from urllib.parse import urlparse

import pytest
import yaml
from selenium.common.exceptions import JavascriptException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumwire import webdriver

CONTROLLER_METADATA = yaml.safe_load(Path("charms/jupyter-controller/metadata.yaml").read_text())
UI_METADATA = yaml.safe_load(Path("charms/jupyter-ui/metadata.yaml").read_text())


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test):
    await ops_test.deploy_bundle(destructive_mode=True, serial=True, extra_args=["--trust"])

    await ops_test.model.block_until(
        lambda: all(
            unit.workload_status == "active" and unit.agent_status == "idle"
            for _, application in ops_test.model.applications.items()
            for unit in application.units
        ),
        timeout=600,
    )

    await ops_test.run(
        "kubectl",
        "create",
        "namespace",
        "kubeflow-user",
    )

    await ops_test.run(
        "kubectl",
        "create",
        "-n",
        "kubeflow-user",
        "serviceaccount",
        "default-editor",
    )


@pytest.fixture()
def driver(request, ops_test):
    env = os.environ.copy()
    env['JUJU_MODEL'] = ops_test.model_name

    gateway_json = check_output(
        [
            'kubectl',
            'get',
            'services/istio-ingressgateway',
            '-n',
            ops_test.model_name,
            '-oyaml',
        ]
    )
    gateway_obj = yaml.safe_load(gateway_json)
    gateway_ip = gateway_obj['status']['loadBalancer']['ingress'][0]['ip']
    url = f'http://{gateway_ip}.nip.io/jupyter/'
    options = Options()
    options.headless = True
    options.log.level = 'trace'

    kwargs = {
        'options': options,
        'seleniumwire_options': {'enable_har': True},
    }

    with webdriver.Firefox(**kwargs) as driver:
        wait = WebDriverWait(driver, 180, 1, (JavascriptException, StopIteration))
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


def test_notebook(driver, ops_test):
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
