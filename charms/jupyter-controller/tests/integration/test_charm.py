# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for Jupyter controller."""
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

log = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
CHARM_NAME = METADATA["name"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Test build and deploy."""
    await ops_test.model.deploy("istio-pilot", channel="1.5/beta")
    await ops_test.model.deploy("jupyter-ui")
    await ops_test.model.add_relation("jupyter-ui", "istio-pilot")

    my_charm = await ops_test.build_charm(".")
    image_path = METADATA["resources"]["oci-image"]["upstream-source"]
    resources = {"oci-image": image_path}
    await ops_test.model.deploy(my_charm, resources=resources)
    await ops_test.model.wait_for_idle(
        status="active", raise_on_blocked=False, raise_on_error=False
    )

    assert ops_test.model.applications[CHARM_NAME].units[0].workload_status == "active"
