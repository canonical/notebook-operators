# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Unit tests for JupyterUI Charm."""

import logging
from unittest.mock import MagicMock, patch

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus
from ops.testing import Harness

from charm import (
    JUPYTER_IMAGES_CONFIG,
    JWA_CONFIG_FILE,
    RSTUDIO_IMAGES_CONFIG,
    VSCODE_IMAGES_CONFIG,
    JupyterUI,
)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="function")
def harness() -> Harness:
    """Create and return Harness for testing."""
    harness = Harness(JupyterUI)

    # setup container networking simulation
    harness.set_can_connect("jupyter-ui", True)

    return harness


class TestCharm:
    """Test class for JupyterUI."""

    def render_spawner_ui_config(self, jupyter_images, vscode_images, rstudio_images):
        """Renders the spawner config template with the config values."""
        environment = Environment(loader=FileSystemLoader("."))
        template = environment.get_template(JWA_CONFIG_FILE)
        yaml_content = template.render(
            jupyter_images=jupyter_images,
            vscode_images=vscode_images,
            rstudio_images=rstudio_images,
        )
        content = yaml.safe_load(yaml_content)
        return content

    def test_spawner_ui(self, harness):
        """Test spawner UI.

        spawner_ui_config.yaml.j2 contains a number of changes that were done for Charmed
        Kubeflow. This test is to validate those. If it fails, spawner_ui_config.yaml.j2
        should be reviewed and changes to this tests should be made, if required.
        """
        # Load the default config for Notebook images lists
        jupyter_images = yaml.safe_load(harness.model.config[JUPYTER_IMAGES_CONFIG])
        vscode_images = yaml.safe_load(harness.model.config[VSCODE_IMAGES_CONFIG])
        rstudio_images = yaml.safe_load(harness.model.config[RSTUDIO_IMAGES_CONFIG])

        # Render the spawner config file with the default configs
        spawner_ui_config = self.render_spawner_ui_config(
            jupyter_images, vscode_images, rstudio_images
        )

        # test for default configurations
        # only single configuration value is currently set in the list of values
        config_value = spawner_ui_config["spawnerFormDefaults"]["configurations"]["value"]
        assert config_value == ["access-ml-pipeline"]

        # test for images added in addition to upstream
        image_list = spawner_ui_config["spawnerFormDefaults"]["image"]["options"]
        assert any(
            "swr.cn-south-1.myhuaweicloud.com/mindspore/jupyter-mindspore" in image
            for image in image_list
        )

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_not_leader(self, k8s_resource_handler: MagicMock, harness: Harness):
        """Test not a leader scenario."""
        harness.begin_with_initial_hooks()
        harness.container_pebble_ready("jupyter-ui")
        assert harness.charm.model.unit.status == WaitingStatus("Waiting for leadership")

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_no_relation(self, k8s_resource_handler: MagicMock, harness: Harness):
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
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_with_relation(self, k8s_resource_handler: MagicMock, harness: Harness):
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
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_pebble_layer(self, k8s_resource_handler: MagicMock, harness: Harness):
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
        assert (
            pebble_plan_info["services"]["jupyter-ui"]["command"]
            == "gunicorn -w 3 --bind 0.0.0.0:5000 --access-logfile - entrypoint:app"
        )
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

    @pytest.mark.parametrize(
        "config_key,expected_images",
        [
            ("jupyter-images", ["jupyterimage1", "jupyterimage2"]),
            ("vscode-images", ["vscodeimage1", "vscodeimage2"]),
            ("rstudio-images", ["rstudioimage1", "rstudioimage2"]),
        ],
    )
    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_notebook_selector_images_config(
        self, k8s_resource_handler: MagicMock, harness: Harness, config_key, expected_images
    ):
        """Test that updating the images config works as expected for:
        Jupyter images, VSCode images, and RStudio images ."""
        expected_images_yaml = yaml.dump(expected_images)
        harness.set_leader(True)
        harness.begin()
        harness.update_config({config_key: expected_images_yaml})
        actual_images = harness.charm._get_from_config(config_key)
        assert actual_images == expected_images

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_render_jwa_file(self, k8s_resource_handler: MagicMock, harness: Harness):
        """Tests the rendering of the jwa spawner file with the list of images."""
        jupyter_images = ["jupyterimage1", "jupyterimage2"]
        vscode_images = ["vscodeimage1", "vscodeimage2"]
        rstudio_images = ["rstudioimage1", "rstudioimage2"]
        harness.set_leader(True)
        harness.begin()
        actual_content_yaml = harness.charm._render_jwa_file_with_images_config(
            jupyter_images, vscode_images, rstudio_images
        )
        actual_content = yaml.safe_load(actual_content_yaml)
        rendered_jupyter_images = actual_content["spawnerFormDefaults"]["image"]["options"]
        rendered_vscode_images = actual_content["spawnerFormDefaults"]["imageGroupOne"]["options"]
        rendered_rstudio_images = actual_content["spawnerFormDefaults"]["imageGroupTwo"]["options"]
        assert rendered_jupyter_images == jupyter_images
        assert rendered_vscode_images == vscode_images
        assert rendered_rstudio_images == rstudio_images

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_upload_jwa_file(self, k8s_resource_handler: MagicMock, harness: Harness):
        """Tests uploading the jwa config file to the container with the right contents."""
        harness.set_leader(True)
        harness.begin()
        test_config = {"config": "test"}
        test_config_yaml = yaml.dump(test_config)
        harness.charm._upload_jwa_file_to_container(test_config_yaml)
        actual_config = yaml.safe_load(
            harness.charm.container.pull("/etc/config/spawner_ui_config.yaml")
        )
        assert actual_config == test_config

    @pytest.mark.parametrize(
        "config_key",
        ["jupyter-images", "vscode-images", "rstudio-images"],
    )
    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_failure_get_config(
        self, k8s_resource_handler: MagicMock, harness: Harness, config_key
    ):
        """Tests that a warning is logged when a Notebook images config contains an invalid YAML."""
        invalid_yaml = "[ invalid yaml"
        harness.update_config({config_key: invalid_yaml})
        harness.set_leader(True)
        harness.begin()
        harness.charm.logger = MagicMock()
        harness.charm._get_from_config(config_key)
        harness.charm.logger.warning.assert_called_once()
