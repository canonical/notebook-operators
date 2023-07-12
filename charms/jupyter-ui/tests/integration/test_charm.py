# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Integration tests for Jupyter UI Operator/Charm."""

import logging
from pathlib import Path

import aiohttp
import pytest
import pytest_asyncio
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
CONFIG = yaml.safe_load(Path("./config.yaml").read_text())
APP_NAME = "jupyter-ui"


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


async def test_ui_is_accessible(ops_test: OpsTest):
    """Verify that UI is accessible."""
    # NOTE: This test is re-using deployment created in test_build_and_deploy()
    # NOTE: This test also tests Pebble checks since it uses the same URL.

    status = await ops_test.model.get_status()
    jupyter_ui_units = status["applications"]["jupyter-ui"]["units"]
    jupyter_ui_url = jupyter_ui_units["jupyter-ui/0"]["address"]

    # obtain status and response text from Jupyter UI URL
    port = CONFIG["options"]["port"]["default"]
    result_status, result_text = await fetch_response(f"http://{jupyter_ui_url}:{port}")

    # verify that UI is accessible (NOTE: this also tests Pebble checks)
    assert result_status == 200
    assert len(result_text) > 0
    assert "Jupyter Management UI" in result_text


@pytest_asyncio.fixture
async def deploy_kubeflow_dashboard(ops_test: OpsTest):
    """Deploys kubeflow-dashboard and kubeflow-profiles, cleaning them up after the usage."""
    kubeflow_profiles = "kubeflow-profiles"
    await ops_test.model.deploy(kubeflow_profiles, channel="stable", trust=True)

    kubeflow_dashboard = "kubeflow-dashboard"
    # Requires latest/edge until https://github.com/canonical/kubeflow-dashboard-operator/pull/134
    # is merged into latest/stable
    ops_test.model.deploy(kubeflow_dashboard, channel="edge", trust=True)

    await ops_test.model.relate(kubeflow_dashboard, kubeflow_profiles)

    await ops_test.model.wait_for_idle(
        apps=[kubeflow_dashboard, kubeflow_profiles], status="active", timeout=60 * 5
    )

    yield kubeflow_dashboard

    # We should remove things, but removal was flaky during initial testing and `block_until_done`
    # does not block successfully.  Try this again once dashboard and profile use chisme
    # KRH.delete to see it they work better
    # ops_test.model.remove_application(kubeflow_dashboard, block_until_done=True)
    # ops_test.model.remove_application(kubeflow_profiles, block_until_done=True)


async def test_dashboard_link_relation(ops_test: OpsTest, deploy_kubeflow_dashboard: str):
    """Test that we can successfully relate to the Kubeflow Dashboard.

    Note: This test only asserts that we establish a relation and both Dashboard or this charm
    successfully go back to Active, it does not actually confirm the links are added to the
    dashboard.  This functionality is tested for in the kubeflow-dashboard repo.
    """
    kubeflow_dashboard_charm_name = deploy_kubeflow_dashboard
    await ops_test.model.relate(APP_NAME, kubeflow_dashboard_charm_name)
    await ops_test.model.wait_for_idle(status="active", timeout=60 * 5)
