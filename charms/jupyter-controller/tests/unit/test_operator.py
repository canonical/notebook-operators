# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import pytest
import yaml
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness

from charm import Operator

"""Test for Jupyter controller."""

@pytest.fixture
def harness():
    return Harness(Operator)

def test_not_leader(harness):
    """Test that charm waits if not leader."""
    harness.begin_with_initial_hooks()
    assert harness.charm.model.unit.status == WaitingStatus("Waiting for leadership")


def test_missing_image(harness):
    """Test if charm is blocked if missing oci-image."""
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    assert harness.charm.model.unit.status == BlockedStatus("Missing resource: oci-image")


def test_no_relation(harness):
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

    spec, k8s = harness.get_pod_spec()
    assert harness.charm.model.unit.status == ActiveStatus("")
    assert spec is not None

    crds = [crd["name"] for crd in k8s["kubernetesResources"]["customResourceDefinitions"]]

    assert crds == ["notebooks.kubeflow.org"]

def test_prometheus_data_set(harness: Harness, mocker):
        """Test Prometheus data setting."""
        harness.set_leader(True)
        harness.set_model_name("test_kubeflow")

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
        harness.begin()

        # basic data
        assert json.loads(
            harness.get_relation_data(rel_id, harness.model.app.name)["scrape_jobs"]
        )[0]["static_configs"][0]["targets"] == ["*:8080"]

        # load alert rules from rules files
        test_alerts = []
        with open("src/prometheus_alert_rules/controller.rule") as f:
            file_alert = yaml.safe_load(f.read())
            test_alerts.append(file_alert["groups"][0]["rules"][0]["alert"])
        with open("src/prometheus_alert_rules/host_resources.rules") as f:
            file_alert = yaml.safe_load(f.read())
            # there 2 alert rules in host_resources.rules
            for rule in file_alert["groups"][0]["rules"]:
                test_alerts.append(rule["alert"])
        with open("src/prometheus_alert_rules/model_errors.rule") as f:
            file_alert = yaml.safe_load(f.read())
            test_alerts.append(file_alert["groups"][0]["rules"][0]["alert"])
        with open("src/prometheus_alert_rules/unit_unavailable.rule") as f:
            file_alert = yaml.safe_load(f.read())
            test_alerts.append(file_alert["groups"][0]["rules"][0]["alert"])

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
