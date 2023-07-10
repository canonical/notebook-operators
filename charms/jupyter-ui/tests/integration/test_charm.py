# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Integration tests for Jupyter UI Operator/Charm."""

import json
import logging
from pathlib import Path

import aiohttp
import pytest
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
CONFIG = yaml.safe_load(Path("./config.yaml").read_text())
APP_NAME = "jupyter-ui"
JUPYTER_IMAGES_CONFIG = "jupyter-images"
PORT = CONFIG["options"]["port"]["default"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build and deploy the charm.

    Assert on the unit status.
    """
    charm_under_test = await ops_test.build_charm(".")
    image_path = METADATA["resources"]["oci-image"]["upstream-source"]
    resources = {"oci-image": image_path}

    await ops_test.model.deploy(
        charm_under_test, resources=resources, application_name=APP_NAME, trust=True
    )

    # NOTE: idle_period is used to ensure all resources are deployed
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", raise_on_blocked=True, timeout=60 * 10, idle_period=30
    )
    assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"


async def fetch_response(url):
    """Fetch provided URL and return pair - status and text (int, string)."""
    result_status = 0
    result_text = ""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            result_status = response.status
            result_text = await response.text()
    return result_status, str(result_text)


async def get_unit_address(ops_test: OpsTest):
    """Returns the unit address of jupyter-ui application."""
    status = await ops_test.model.get_status()
    jupyter_ui_units = status["applications"]["jupyter-ui"]["units"]
    jupyter_ui_url = jupyter_ui_units["jupyter-ui/0"]["address"]
    return jupyter_ui_url


async def test_ui_is_accessible(ops_test: OpsTest):
    """Verify that UI is accessible."""
    # NOTE: This test is re-using deployment created in test_build_and_deploy()
    # NOTE: This test also tests Pebble checks since it uses the same URL.
    jupyter_ui_url = await get_unit_address(ops_test)

    # obtain status and response text from Jupyter UI URL
    result_status, result_text = await fetch_response(f"http://{jupyter_ui_url}:{PORT}")

    # verify that UI is accessible (NOTE: this also tests Pebble checks)
    assert result_status == 200
    assert len(result_text) > 0
    assert "Jupyter Management UI" in result_text


async def test_notebook_image_selector(ops_test: OpsTest):
    """
    Verify that setting the juju config `jupyter-images` sets the notebook images selector list,
    with the same value in the config.
    """
    expected_images = ["image1", "image2", "image3"]
    await ops_test.model.applications[APP_NAME].set_config(
        {JUPYTER_IMAGES_CONFIG: yaml.dump(expected_images)}
    )
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", raise_on_blocked=True, timeout=60 * 10, idle_period=30
    )
    jupyter_ui_url = await get_unit_address(ops_test)
    response = await fetch_response(f"http://{jupyter_ui_url}:{PORT}/api/config")
    response_json = json.loads(response[1])
    assert response_json["config"]["image"]["options"] == expected_images
