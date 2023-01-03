# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Unit tests for JupyterUI Charm."""

from unittest.mock import MagicMock, patch

import pytest
import yaml
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus
from ops.testing import Harness

from charm import JupyterUI


@pytest.fixture(scope="function")
def harness() -> Harness:
    """Create and return Harness for testing."""
    harness = Harness(JupyterUI)

    # setup container networking simulation
    harness.set_can_connect("jupyter-ui", True)

    return harness


class TestCharm:
    """Test class for JupyterUI."""

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    def test_not_leader(self, harness: Harness):
        """Test not a leader scenario."""
        harness.begin_with_initial_hooks()
        harness.container_pebble_ready("jupyter-ui")
        assert harness.charm.model.unit.status == WaitingStatus("Waiting for leadership")

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    def test_no_relation(self, harness: Harness):
        """Test no relation scenario."""
        harness.set_leader(True)
        harness.add_oci_resource(
            "oci-image",
            {
                "registrypath": "ci-test",
                "username": "",
                "password": "",
            },
        )
        harness.begin_with_initial_hooks()
        harness.container_pebble_ready("jupyter-ui")
        assert harness.charm.model.unit.status == ActiveStatus("")

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    def test_with_relation(self, harness: Harness):
        harness.set_leader(True)
        harness.add_oci_resource(
            "oci-image",
            {
                "registrypath": "ci-test",
                "username": "",
                "password": "",
            },
        )
        rel_id = harness.add_relation("ingress", "istio-pilot")

        harness.add_relation_unit(rel_id, "istio-pilot/0")
        data = {"service-name": "service-name", "service-port": "6666"}
        harness.update_relation_data(
            rel_id,
            "istio-pilot",
            {"_supported_versions": "- v1", "data": yaml.dump(data)},
        )
        harness.begin_with_initial_hooks()

        assert isinstance(harness.charm.model.unit.status, ActiveStatus)

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    def test_pebble_layer(self, harness: Harness):
        """Test creation of Pebble layer. Only test specific items."""
        harness.set_leader(True)
        harness.add_oci_resource(
            "oci-image",
            {
                "registrypath": "ci-test",
                "username": "",
                "password": "",
            },
        )
        harness.set_model_name("kubeflow")
        harness.begin_with_initial_hooks()
        harness.container_pebble_ready("jupyter-ui")
        assert harness.charm.container.get_service("jupyter-ui").is_running()
        pebble_plan = harness.get_container_pebble_plan("jupyter-ui")
        assert pebble_plan
        assert pebble_plan.services
        pebble_plan_info = pebble_plan.to_dict()
        assert pebble_plan_info["services"]["jupyter-ui"]["command"] == "npm start"
        test_env = pebble_plan_info["services"]["jupyter-ui"]["environment"]
        # there should be 7 environment variables
        assert 7 == len(test_env)
        assert "cluster.local" == test_env["CLUSTER_DOMAIN"]

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_deploy_k8s_resources_success(
        self,
        k8s_resource_handler: MagicMock,
        harness: Harness,
    ):
        """Test if K8S resource handler is executed as expected."""
        harness.begin()
        harness.charm._deploy_k8s_resources()
        k8s_resource_handler.apply.assert_called()
        assert isinstance(harness.charm.model.unit.status, MaintenanceStatus)
