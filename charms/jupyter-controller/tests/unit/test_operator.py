# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for Jupyter controller."""

import json
from unittest.mock import MagicMock, patch

import pytest
import yaml
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.testing import Harness

from charm import JupyterController


@pytest.fixture(scope="function")
def harness() -> Harness:
    """Create and return Harness for testing.

    Make the harness a leader and set a model name so tests don't need to repeat this setup.
    """
    harness = Harness(JupyterController)

    # set a model name expected by the charm's service_environment
    harness.set_model_name("kubeflow")

    # make this unit a leader by default to avoid leader-guarded codepaths in tests
    harness.set_leader(True)

    # setup container networking simulation
    harness.set_can_connect("jupyter-controller", True)

    return harness


class TestCharm:
    """Test class for JupyterController."""

    @patch("charm.KubernetesServicePatch")
    @patch("charm.LogForwarder")
    def test_log_forwarding(
        self, mock_logging: MagicMock, mock_service_patch: MagicMock, harness: Harness
    ):
        harness.begin()
        mock_logging.assert_called_once_with(charm=harness.charm)

    @patch("charm.KubernetesServicePatch", lambda *_, **__: None)
    @patch("charm.JupyterController.k8s_resource_handler")
    @patch("charm.JupyterController.crd_resource_handler")
    def test_not_leader(
        self,
        k8s_resource_handler: MagicMock,
        crd_resource_handler: MagicMock,
        harness: Harness,
    ):
        """Test that charm waits if not leader."""
        harness.set_leader(False)
        harness.begin_with_initial_hooks()
        harness.container_pebble_ready("jupyter-controller")
        assert harness.charm.model.unit.status == WaitingStatus("Waiting for leadership")

    @patch("charm.KubernetesServicePatch", lambda *_, **__: None)
    @patch("charm.JupyterController.k8s_resource_handler")
    @patch("charm.JupyterController.crd_resource_handler")
    def test_no_relation(
        self,
        k8s_resource_handler: MagicMock,
        crd_resource_handler: MagicMock,
        harness: Harness,
    ):
        """Test charm blocks until the required service mesh relation is added."""
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
        assert harness.charm.model.unit.status == BlockedStatus(
            "Missing required relation: service-mesh"
        )

    @pytest.mark.parametrize("gateway_related", [False, True])
    @patch("charm.KubernetesServicePatch", lambda *_, **__: None)
    @patch("charm.JupyterController.k8s_resource_handler", MagicMock())
    @patch("charm.JupyterController.crd_resource_handler", MagicMock())
    def test_waiting_for_gateway(self, harness: Harness, gateway_related):
        """Block without a gateway relation, but wait for data on an existing relation."""
        harness.add_relation("service-mesh", "istio-beacon")
        if gateway_related:
            harness.add_relation("gateway-metadata", "istio-ingress-k8s")
        harness.begin_with_initial_hooks()
        expected = (
            WaitingStatus("Waiting for gateway metadata relation data")
            if gateway_related
            else BlockedStatus("Missing required relation: gateway-metadata")
        )
        assert harness.model.unit.status == expected
        assert not harness.get_container_pebble_plan("jupyter-controller").services

    @patch("charm.KubernetesServicePatch", lambda *_, **__: None)
    @patch("charm.JupyterController.k8s_resource_handler", MagicMock())
    @patch("charm.JupyterController.crd_resource_handler", MagicMock())
    @patch("charm.ServiceMeshConsumer", MagicMock)
    def test_service_mesh_removed(self, harness: Harness):
        """Remain blocked after losing the mesh, including during update-status."""
        mesh_id = harness.add_relation("service-mesh", "istio-beacon")
        harness.add_relation("gateway-metadata", "istio-ingress-k8s")
        with patch("charm.GatewayMetadataRequirer.get_metadata") as get_metadata:
            get_metadata.return_value.namespace = "kubeflow"
            get_metadata.return_value.gateway_name = "ambient-gateway"
            harness.begin_with_initial_hooks()
            assert harness.model.unit.status == ActiveStatus()
            harness.remove_relation(mesh_id)
            assert harness.model.unit.status == BlockedStatus(
                "Missing required relation: service-mesh"
            )
            harness.charm.on.update_status.emit()
            assert harness.model.unit.status == BlockedStatus(
                "Missing required relation: service-mesh"
            )

    @patch("charm.KubernetesServicePatch", lambda *_, **__: None)
    def test_prometheus_data_set(self, harness: Harness, mocker):
        """Test Prometheus data setting."""
        harness.begin()

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
        # Uncomment once https://github.com/canonical/notebook-operators/issues/409
        # is fixed.
        # with open("src/prometheus_alert_rules/model_errors.rule") as f:
        #     file_alert = yaml.safe_load(f.read())
        #     test_alerts.append(file_alert["alert"])
        with open("src/prometheus_alert_rules/KubeflowJupyterControllerServices.rules") as f:
            file_alert = yaml.safe_load(f.read())
            # there 2 alert rules in host_resources.rules
            for rule in file_alert["groups"][0]["rules"]:
                test_alerts.append(rule["alert"])

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

    @patch("charm.KubernetesServicePatch", lambda *_, **__: None)
    @patch("charm.JupyterController.k8s_resource_handler")
    @patch("charm.JupyterController.crd_resource_handler")
    def test_pebble_layer(
        self,
        k8s_resource_handler: MagicMock,
        crd_resource_handler: MagicMock,
        harness: Harness,
    ):
        """Test creation of Pebble layer. Only test specific items."""
        harness.add_oci_resource(
            "oci-image",
            {
                "registrypath": "ci-test",
                "username": "",
                "password": "",
            },
        )
        harness.add_relation("service-mesh", "istio-beacon")
        harness.add_relation("gateway-metadata", "istio-ingress-k8s")
        with patch("charm.GatewayMetadataRequirer.get_metadata") as get_metadata:
            get_metadata.return_value.namespace = "kubeflow"
            get_metadata.return_value.gateway_name = "ambient-gateway"
            harness.begin_with_initial_hooks()
            harness.container_pebble_ready("jupyter-controller")
        assert harness.charm.container.get_service("jupyter-controller").is_running()
        pebble_plan = harness.get_container_pebble_plan("jupyter-controller")
        assert pebble_plan
        assert pebble_plan.services
        pebble_plan_info = pebble_plan.to_dict()
        assert pebble_plan_info["services"]["jupyter-controller"]["command"] == "./manager"
        test_env = pebble_plan_info["services"]["jupyter-controller"]["environment"]
        assert test_env["USE_ISTIO"] == "false"
        assert test_env["EXPERIMENTAL_USE_GATEWAY_API"] == "true"
        assert test_env["EXPERIMENTAL_K8S_GATEWAY_NAMESPACE"] == "kubeflow"
        assert test_env["EXPERIMENTAL_K8S_GATEWAY_NAME"] == "ambient-gateway"
        assert "ISTIO_GATEWAY" not in test_env
        assert "ISTIO_HOST" not in test_env

    @patch("charm.KubernetesServicePatch", lambda *_, **__: None)
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

    @patch("charm.KubernetesServicePatch", lambda *_, **__: None)
    @patch("charm.JupyterController._apply_k8s_resources")
    @patch("charm.JupyterController._check_status")
    def test_update_status(
        self,
        _apply_k8s_resources: MagicMock,
        _check_status: MagicMock,
        harness: Harness,
    ):
        """Test update status handler."""
        harness.begin_with_initial_hooks()
        harness.container_pebble_ready("jupyter-controller")

        # test successful update status
        harness.charm.on.update_status.emit()
        _apply_k8s_resources.assert_called()
        _check_status.assert_called()
