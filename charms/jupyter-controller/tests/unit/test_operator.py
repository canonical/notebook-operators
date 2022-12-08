# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Test for Jupyter controller."""
import pytest
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness

from charm import Operator

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
