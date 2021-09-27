from pathlib import Path
from random import choices
from string import ascii_lowercase
from subprocess import check_output
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


@pytest.fixture()
def driver(request):
    status = yaml.safe_load(check_output(['juju', 'status', '--format=yaml']))
    endpoint = status['applications']['istio-ingressgateway']['address']
    url = f'http://{endpoint}.nip.io/jupyter/'
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
                break
            except WebDriverException:
                sleep(5)
        else:
            driver.get(url)

        yield driver, wait, url

        Path(f'/tmp/selenium-{request.node.name}.har').write_text(driver.har)
        driver.get_screenshot_as_file(f'/tmp/selenium-{request.node.name}.png')


def test_notebook(driver):
    """Ensures a notebook can be created and connected to."""

    driver, wait, url = driver

    notebook_name = 'ci-test-' + ''.join(choices(ascii_lowercase, k=10))

    # Click "New Server" button
    driver.find_element_by_id("newResource").click()
    wait.until(EC.url_to_be(url + 'new'))

    # Enter server name
    name_input = driver.find_element_by_css_selector('input[placeholder="Name"]')
    name_input.send_keys(notebook_name)
    name_input.click()

    # Click submit on the form. Sleep for 1 second before clicking the submit
    # button because shiny animations that ignore click events are simply a must.
    # Note that that was sarcasm. If you're reading this, please don't shit up
    # the web with braindead technologies.
    submit = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".form--button-margin.mat-primary:not(disabled)")
        )
    )
    sleep(1)
    submit.click()
    wait.until(EC.url_to_be(url))

    # Since upstream doesn't use proper class names or IDs or anything, find the
    # <tr> containing elements that contain the notebook name and `ready`, signifying
    # that the notebook is finished booting up. Returns a reference to the containing
    # <tr> element. The result is a fairly unreadable XPath reference, but it works 🤷
    chonky_boi = '/'.join(
        [
            f"//*[contains(text(), '{notebook_name}')]",
            "ancestor::tr",
            "/*[contains(@class, 'ready')]",
            "ancestor::tr",
        ]
    )
    row = wait.until(EC.presence_of_element_located((By.XPATH, chonky_boi)))
    print(driver.window_handles)
    row.find_element_by_class_name('action-button').click()
    print(driver.window_handles)

    # Make sure we can connect to a specific notebook's endpoint
    # Notebook is opened in a new tab, so we have to explicitly switch to it,
    # run our tests, close it, then switch back to the main window.
    driver.switch_to.window(driver.window_handles[-1])
    expected_path = '/notebook/kubeflow-user/%s/lab' % notebook_name
    for _ in range(60):
        path = urlparse(driver.current_url).path
        if path == expected_path:
            break

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
    row.find_element_by_xpath("//*[contains(text(), 'delete')]").click()
    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "mat-warn"))).click()
    wait.until_not(
        EC.presence_of_element_located((By.XPATH, f"//*[contains(text(), '{notebook_name}')]"))
    )
