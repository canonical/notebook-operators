# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Integration tests for Jupyter UI Operator/Charm."""

import json
import logging
from pathlib import Path

import aiohttp
import dpath
import pytest
import tenacity
import yaml
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


async def fetch_response(url, headers=None):
    """Fetch provided URL and return pair - status and text (int, string)."""
    result_status = 0
    result_text = ""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            result_status = response.status
            result_text = await response.text()
    return result_status, str(result_text)


async def get_unit_address(ops_test: OpsTest):
    """Return the unit address of jupyter-ui application."""
    status = await ops_test.model.get_status()
    jupyter_ui_units = status["applications"]["jupyter-ui"]["units"]
    jupyter_ui_url = jupyter_ui_units["jupyter-ui/0"]["address"]
    return jupyter_ui_url


@pytest.mark.abort_on_fail
async def test_ui_is_accessible(ops_test: OpsTest):
    """Verify that UI is accessible."""
    # NOTE: This test is re-using deployment created in test_build_and_deploy()
    # NOTE: This test also tests Pebble checks since it uses the same URL.
    jupyter_ui_url = await get_unit_address(ops_test)

    # obtain status and response text from Jupyter UI URL
    result_status, result_text = await fetch_response(f"http://{jupyter_ui_url}:{PORT}", HEADERS)

    # verify that UI is accessible (NOTE: this also tests Pebble checks)
    assert result_status == 200
    assert len(result_text) > 0
    assert "Jupyter Management UI" in result_text


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
    expected_images = config_value

    # To avoid waiting for a long idle_period between each of this series of tests, we do not use
    # wait_for_idle.  Instead we push the config and then try for 120 seconds to assert the config
    # is updated.  This ends up being faster than waiting for idle_period between each test.

    jupyter_ui_url = await get_unit_address(ops_test)
    logger.info("Polling the Jupyter UI API to check the configuration")
    for attempt in RETRY_120_SECONDS:
        logger.info("Testing whether the config has been updated")
        with attempt:
            try:
                response = await fetch_response(
                    f"http://{jupyter_ui_url}:{PORT}/api/config", HEADERS
                )
                response_json = json.loads(response[1])
                actual_config = dpath.get(response_json, yaml_path)
                assert actual_config == expected_images
            except AssertionError as e:
                logger.info("Failed assertion that config is updated - will retry")
                raise e


RETRY_120_SECONDS = tenacity.Retrying(
    stop=tenacity.stop_after_delay(120),
    wait=tenacity.wait_fixed(2),
    reraise=True,
)
