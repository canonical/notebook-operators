# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for Jupyter controller."""

import json
from unittest.mock import MagicMock, patch

import pytest
import yaml
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus
from ops.testing import Harness

from charm import JupyterController


@pytest.fixture(scope="function")
def harness() -> Harness:
    """Create and return Harness for testing."""
    harness = Harness(JupyterController)

    # setup container networking simulation
    harness.set_can_connect("jupyter-controller", True)

    return harness


class TestCharm:
    """Test class for JupyterController."""

    @patch("charm.JupyterController.k8s_resource_handler")
    @patch("charm.JupyterController.crd_resource_handler")
    def test_not_leader(
        self,
        k8s_resource_handler: MagicMock,
        crd_resource_handler: MagicMock,
        harness: Harness,
    ):
        """Test that charm waits if not leader."""
        harness.begin_with_initial_hooks()
        harness.container_pebble_ready("jupyter-controller")
        assert harness.charm.model.unit.status == WaitingStatus("Waiting for leadership")

    @patch("charm.JupyterController.k8s_resource_handler")
    @patch("charm.JupyterController.crd_resource_handler")
    def test_no_relation(
        self,
        k8s_resource_handler: MagicMock,
        crd_resource_handler: MagicMock,
        harness: Harness,
    ):
        """Test charm goes to active if no additional relations exist."""
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
        harness.container_pebble_ready("jupyter-controller")
        assert harness.charm.model.unit.status == ActiveStatus("")

    def test_prometheus_data_set(self, harness: Harness, mocker):
        """Test Prometheus data setting."""
        harness.set_leader(True)
        harness.set_model_name("test_kubeflow")
        harness.begin()

        mock_net_get = mocker.patch("ops.testing._TestingModelBackend.network_get")

        bind_address = "1.1.1.1"
        fake_network = {
            "bind-addresses": [
                {
                    "interface-name": "eth0",
                    "addresses": [{"hostname": "cassandra-tester-0", "value": bind_address}],
                }
            ]
        }
        mock_net_get.return_value = fake_network

        rel_id = harness.add_relation("metrics-endpoint", "otherapp")
        harness.add_relation_unit(rel_id, "otherapp/0")
        harness.update_relation_data(rel_id, "otherapp", {})

        # basic data
        assert json.loads(
            harness.get_relation_data(rel_id, harness.model.app.name)["scrape_jobs"]
        )[0]["static_configs"][0]["targets"] == ["*:8080"]

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

        # alert rules
        alert_rules = json.loads(
            harness.get_relation_data(rel_id, harness.model.app.name)["alert_rules"]
        )
        assert alert_rules is not None
        assert alert_rules["groups"] is not None

        # there are 5 alerts
        rules = []
        for group in alert_rules["groups"]:
            for rule in group["rules"]:
                rules.append(rule)

        # verify number of alerts is the same in relation and in the rules file
        assert len(rules) == len(test_alerts)

        # verify alerts in relation match alerts in the rules file
        for rule in rules:
            assert rule["alert"] in test_alerts

    @patch("charm.JupyterController.k8s_resource_handler")
    @patch("charm.JupyterController.crd_resource_handler")
    def test_pebble_layer(
        self,
        k8s_resource_handler: MagicMock,
        crd_resource_handler: MagicMock,
        harness: Harness,
    ):
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
        harness.container_pebble_ready("jupyter-controller")
        assert harness.charm.container.get_service("jupyter-controller").is_running()
        pebble_plan = harness.get_container_pebble_plan("jupyter-controller")
        assert pebble_plan
        assert pebble_plan.services
        pebble_plan_info = pebble_plan.to_dict()
        assert pebble_plan_info["services"]["jupyter-controller"]["command"] == "./manager"
        test_env = pebble_plan_info["services"]["jupyter-controller"]["environment"]
        # there should be 3 environment variables
        assert 3 == len(test_env)
        assert "kubeflow/kubeflow-gateway" == test_env["ISTIO_GATEWAY"]

    @patch("charm.JupyterController.k8s_resource_handler")
    @patch("charm.JupyterController.crd_resource_handler")
    def test_deploy_k8s_resources_success(
        self,
        k8s_resource_handler: MagicMock,
        crd_resource_handler: MagicMock,
        harness: Harness,
    ):
        """Test if K8S resource handler is executed as expected."""
        harness.begin()
        harness.charm._apply_k8s_resources()
        k8s_resource_handler.apply.assert_called()
        assert isinstance(harness.charm.model.unit.status, MaintenanceStatus)

    @patch("charm.JupyterController._apply_k8s_resources")
    @patch("charm.JupyterController._check_status")
    def test_update_status(
        self,
        _apply_k8s_resources: MagicMock,
        _check_status: MagicMock,
        harness: Harness,
    ):
        """Test update status handler."""
        harness.set_leader(True)
        harness.begin_with_initial_hooks()
        harness.container_pebble_ready("jupyter-controller")
        harness.charm.on.update_status.emit()
        _apply_k8s_resources.assert_called()
        _check_status.assert_called()
