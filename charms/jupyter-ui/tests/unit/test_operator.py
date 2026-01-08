# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""Unit tests for JupyterUI Charm."""

import copy
import logging
from contextlib import nullcontext as does_not_raise
from pathlib import Path
from re import match
from unittest.mock import MagicMock, patch

import pytest
import yaml
from charmed_kubeflow_chisme.exceptions import ErrorWithStatus
from charmed_kubeflow_chisme.testing import ISTIO_INGRESS_K8S_APP, ISTIO_INGRESS_ROUTE_ENDPOINT
from lightkube.models.core_v1 import (
    Affinity,
    NodeAffinity,
    NodeSelector,
    NodeSelectorRequirement,
    NodeSelectorTerm,
    Toleration,
)
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.testing import Harness

from charm import DEFAULT_JUPYTER_IMAGES_FILE, JupyterUI
from config_validators import ConfigValidationError, OptionsWithDefault

logger = logging.getLogger(__name__)

INGRESS_ENDPOINT = "ingress"
ISTIO_PILOT_APP = "istio-pilot"

# Sample inputs for render_jwa_file tests
JUPYTER_IMAGES_CONFIG = ["jupyterimage1", "jupyterimage2"]
VSCODE_IMAGES_CONFIG = ["vscodeimage1", "vscodeimage2"]
RSTUDIO_IMAGES_CONFIG = ["rstudioimage1", "rstudioimage2"]
AFFINITY_OPTIONS_CONFIG = [
    {
        "configKey": "test-affinity-config-1",
        "displayName": "Test Affinity Config-1",
        "affinity": Affinity(
            nodeAffinity=NodeAffinity(
                requiredDuringSchedulingIgnoredDuringExecution=NodeSelector(
                    [
                        NodeSelectorTerm(
                            matchExpressions=[
                                NodeSelectorRequirement(
                                    key="lifecycle",
                                    operator="In",
                                    values=["kubeflow-notebook-1"],
                                )
                            ]
                        )
                    ]
                )
            )
        ).to_dict(),
    },
    {
        "configKey": "test-affinity-config-2",
        "displayName": "Test Affinity Config-2",
        "affinity": Affinity(
            nodeAffinity=NodeAffinity(
                requiredDuringSchedulingIgnoredDuringExecution=NodeSelector(
                    [
                        NodeSelectorTerm(
                            matchExpressions=[
                                NodeSelectorRequirement(
                                    key="lifecycle",
                                    operator="In",
                                    values=["kubeflow-notebook-2"],
                                )
                            ]
                        )
                    ]
                )
            )
        ).to_dict(),
    },
]
GPU_VENDORS_CONFIG = [
    {"limitsKey": "nvidia", "uiName": "NVIDIA"},
]
TOLERATIONS_OPTIONS_CONFIG = [
    {
        "groupKey": "test-tolerations-group-1",
        "displayName": "Test Tolerations Group 1",
        "tolerations": [
            Toleration(
                effect="NoSchedule",
                key="dedicated",
                operator="Equal",
                value="big-machine",
            ).to_dict()
        ],
    },
    {
        "groupKey": "test-tolerations-group-2",
        "displayName": "Test Tolerations Group 2",
        "tolerations": [
            Toleration(
                effect="NoSchedule",
                key="dedicated",
                operator="Equal",
                value="big-machine",
            ).to_dict()
        ],
    },
]
DEFAULT_PODDEFAULTS_CONFIG = [
    "poddefault1",
    "poddefault2",
]


@pytest.fixture(scope="function")
def harness() -> Harness:
    """Create and return Harness for testing."""
    harness = Harness(JupyterUI)

    # setup container networking simulation
    harness.set_can_connect("jupyter-ui", True)

    # set model name to avoid validation errors
    harness.set_model_name("kubeflow")

    # set leader by default
    harness.set_leader(True)

    yield harness

    harness.cleanup()


class TestCharm:
    """Test class for JupyterUI."""

    @patch("charm.KubernetesServicePatch", MagicMock)
    @patch("charm.JupyterUI.k8s_resource_handler", MagicMock)
    def test_log_forwarding(self, harness: Harness):
        """Test initialization LogForwarder."""
        with patch("charm.LogForwarder") as mock_logging:
            harness.begin()
            mock_logging.assert_called_once_with(charm=harness.charm)

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_spawner_ui(self, k8s_resource_handler: MagicMock, harness: Harness):
        """Test spawner UI.

        spawner_ui_config.yaml.j2 contains a number of changes that were done for Charmed
        Kubeflow. This test is to validate those. If it fails, spawner_ui_config.yaml.j2
        should be reviewed and changes to this tests should be made, if required.
        """
        harness.add_storage("config")
        harness.add_storage("logos")
        harness.begin_with_initial_hooks()

        spawner_ui_config = yaml.safe_load(
            harness.charm.container.pull("/etc/config/spawner_ui_config.yaml")
        )

        # test for default configurations
        # only single configuration value is currently set in the list of values
        config_value = spawner_ui_config["spawnerFormDefaults"]["configurations"]["value"]
        assert config_value == ["access-ml-pipeline"]

    @pytest.mark.parametrize(
        "num_gpus, context_raised",
        [
            (0, does_not_raise()),
            (1, does_not_raise()),
            (2, does_not_raise()),
            (4, does_not_raise()),
            (8, does_not_raise()),
        ],
    )
    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_spawner_ui_has_correct_num_gpu(
        self,
        k8s_resource_handler: MagicMock,
        harness: Harness,
        num_gpus: int,
        context_raised,
    ):
        """Test spawner UI.

        spawner_ui_config.yaml.j2 contains a number of changes that were done for Charmed
        Kubeflow. This test is to validate those. If it fails, spawner_ui_config.yaml.j2
        should be reviewed and changes to this tests should be made, if required.
        """
        harness.add_storage("config")
        harness.add_storage("logos")
        harness.update_config({"gpu-number-default": num_gpus})
        harness.begin_with_initial_hooks()

        spawner_ui_config = yaml.safe_load(
            harness.charm.container.pull("/etc/config/spawner_ui_config.yaml")
        )

        # test for default configurations
        # only single configuration value is currently set in the list of values
        config_value = spawner_ui_config["spawnerFormDefaults"]["gpus"]["value"]["num"]
        if num_gpus == 0:
            assert config_value == "none"
        else:
            assert config_value == num_gpus

    @pytest.mark.parametrize(
        "num_gpus, context_raised",
        [
            # Invalid number
            (3, pytest.raises(ConfigValidationError)),
            # Nonsense input
            ("adsda", pytest.raises(RuntimeError)),
        ],
    )
    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_spawner_ui_for_incorrect_gpu_number(
        self,
        k8s_resource_handler: MagicMock,
        harness: Harness,
        num_gpus: int,
        context_raised,
    ):
        """Test spawner UI.

        spawner_ui_config.yaml.j2 contains a number of changes that were done for Charmed
        Kubeflow. This test is to validate those. If it fails, spawner_ui_config.yaml.j2
        should be reviewed and changes to this tests should be made, if required.
        """
        with context_raised:
            harness.add_storage("config")
            harness.add_storage("logos")
            harness.update_config({"gpu-number-default": num_gpus})
            harness.begin_with_initial_hooks()

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_not_leader(self, k8s_resource_handler: MagicMock, harness: Harness):
        """Test not a leader scenario."""
        harness.set_leader(False)
        harness.add_storage("config")
        harness.add_storage("logos")
        harness.begin_with_initial_hooks()
        harness.container_pebble_ready("jupyter-ui")
        assert harness.charm.model.unit.status == WaitingStatus("Waiting for leadership")

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    @pytest.mark.parametrize(
        "missing_storage",
        ["config", "logos"],
        ids=["missing-config-storage", "missing-logos-storage"],
    )
    def test_no_storage_available(
        self, k8s_resource_handler: MagicMock, harness: Harness, missing_storage: str
    ):
        """Test no storage available scenario."""
        harness.set_leader(True)
        harness.begin()
        if missing_storage == "config":
            harness.add_storage("logos")
        else:
            harness.add_storage("config")

        with pytest.raises(ErrorWithStatus) as exception_info:
            harness.container_pebble_ready("jupyter-ui")

            assert exception_info.value.status_type(WaitingStatus)
            assert match("Storage .* not yet available", str(exception_info))
            assert isinstance(harness.charm.model.unit.status, WaitingStatus)
            assert match("Waiting for .* storage", harness.charm.model.unit.status.message)

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_no_relation(self, k8s_resource_handler: MagicMock, harness: Harness):
        """Test no relation scenario."""
        harness.add_oci_resource(
            "oci-image",
            {
                "registrypath": "ci-test",
                "username": "",
                "password": "",
            },
        )
        harness.add_storage("config")
        harness.add_storage("logos")
        harness.begin_with_initial_hooks()
        harness.container_pebble_ready("jupyter-ui")
        assert harness.charm.model.unit.status == ActiveStatus("")

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_with_relation(self, k8s_resource_handler: MagicMock, harness: Harness):
        """Test charm with relation."""
        harness.add_oci_resource(
            "oci-image",
            {
                "registrypath": "ci-test",
                "username": "",
                "password": "",
            },
        )
        rel_id = harness.add_relation(INGRESS_ENDPOINT, ISTIO_PILOT_APP)

        harness.add_relation_unit(rel_id, f"{ISTIO_PILOT_APP}/0")
        data = {"service-name": "service-name", "service-port": "6666"}
        harness.update_relation_data(
            rel_id,
            ISTIO_PILOT_APP,
            {"_supported_versions": "- v1", "data": yaml.dump(data)},
        )
        harness.add_storage("config")
        harness.add_storage("logos")
        harness.begin_with_initial_hooks()

        assert isinstance(harness.charm.model.unit.status, ActiveStatus)

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_pebble_layer(self, k8s_resource_handler: MagicMock, harness: Harness):
        """Test creation of Pebble layer. Only test specific items."""
        harness.add_oci_resource(
            "oci-image",
            {
                "registrypath": "ci-test",
                "username": "",
                "password": "",
            },
        )
        harness.set_model_name("kubeflow")
        harness.add_storage("config")
        harness.add_storage("logos")
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
        "config_key,expected_config_yaml",
        [
            ("jupyter-images", yaml.dump(["jupyterimage1", "jupyterimage2"])),
            ("vscode-images", yaml.dump(["vscodeimage1", "vscodeimage2"])),
            ("rstudio-images", yaml.dump(["rstudioimage1", "rstudioimage2"])),
            ("jupyter-images", yaml.dump([])),
            ("jupyter-images", ""),
            # poddefaults inputs function like an image selector, so test them here too
            ("default-poddefaults", yaml.dump(DEFAULT_PODDEFAULTS_CONFIG)),
            ("default-poddefaults", ""),
        ],
    )
    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_notebook_selector_config(
        self,
        k8s_resource_handler: MagicMock,
        harness: Harness,
        config_key,
        expected_config_yaml,
    ):
        """Test that updating the images config and poddefaults works as expected.

        The following should be tested:
        Jupyter images, VSCode images, and RStudio images.
        """
        # Arrange
        expected_config = yaml.safe_load(expected_config_yaml)

        # Recast an empty input as an empty list to match the expected output
        if config_key == "jupyter-images" and expected_config_yaml == "":
            expected_config = yaml.safe_load(Path(DEFAULT_JUPYTER_IMAGES_FILE).read_text())

        if expected_config is None:
            expected_config = []

        harness.begin()
        harness.update_config({config_key: expected_config_yaml})

        # Act
        parsed_config = harness.charm._get_from_config(config_key)

        # Assert
        assert parsed_config.options == expected_config
        if expected_config:
            assert parsed_config.default == expected_config[0]
        else:
            assert parsed_config.default == ""

    @pytest.mark.parametrize(
        "config_key,default_value,config_as_yaml",
        [
            (
                "affinity-options",
                "test-affinity-config-1",
                yaml.dump(AFFINITY_OPTIONS_CONFIG),
            ),
            ("gpu-vendors", "nvidia", yaml.dump(GPU_VENDORS_CONFIG)),
            (
                "tolerations-options",
                "test-tolerations-group-1",
                yaml.dump(TOLERATIONS_OPTIONS_CONFIG),
            ),
        ],
    )
    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_notebook_configurations(
        self,
        k8s_resource_handler: MagicMock,
        harness: Harness,
        config_key,
        default_value,
        config_as_yaml,
    ):
        """Test that updating the notebook configuration settings works as expected."""
        # Arrange
        expected_config = yaml.safe_load(config_as_yaml)
        # Recast an empty input as an empty list to match the expected output
        if expected_config is None:
            expected_config = []
        harness.begin()
        harness.update_config({config_key: config_as_yaml})
        harness.update_config({config_key + "-default": default_value})

        # Act
        parsed_config = harness.charm._get_from_config(config_key)

        # Assert
        assert parsed_config.options == expected_config
        assert parsed_config.default == default_value

    @pytest.mark.parametrize(
        "render_jwa_file_with_images_config_args",
        [
            # All options empty
            (
                dict(
                    jupyter_images_config=OptionsWithDefault(),
                    vscode_images_config=OptionsWithDefault(),
                    rstudio_images_config=OptionsWithDefault(),
                    gpu_number_default=0,
                    gpu_vendors_config=OptionsWithDefault(),
                    affinity_options_config=OptionsWithDefault(),
                    tolerations_options_config=OptionsWithDefault(),
                    default_poddefaults_config=OptionsWithDefault(),
                )
            ),
            # All options with valid input
            (
                dict(
                    jupyter_images_config=OptionsWithDefault(
                        default="jupyterimage1",
                        options=["jupyterimage1", "jupyterimage2"],
                    ),
                    vscode_images_config=OptionsWithDefault(
                        default="vscodeimage1", options=["vscodeimage1", "vscodeimage2"]
                    ),
                    rstudio_images_config=OptionsWithDefault(
                        default="rstudioimage1",
                        options=["rstudioimage1", "rstudioimage2"],
                    ),
                    gpu_number_default=1,
                    gpu_vendors_config=OptionsWithDefault(
                        default="nvidia", options=GPU_VENDORS_CONFIG
                    ),
                    affinity_options_config=OptionsWithDefault(
                        default="test-affinity-config-1",
                        options=AFFINITY_OPTIONS_CONFIG,
                    ),
                    tolerations_options_config=OptionsWithDefault(
                        default="test-tolerations-group-1",
                        options=TOLERATIONS_OPTIONS_CONFIG,
                    ),
                    default_poddefaults_config=OptionsWithDefault(
                        default="", options=DEFAULT_PODDEFAULTS_CONFIG
                    ),
                )
            ),
        ],
    )
    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_render_jwa_file(
        self,
        k8s_resource_handler: MagicMock,
        harness: Harness,
        render_jwa_file_with_images_config_args,
    ):
        """Tests the rendering of the jwa spawner file with the list of images."""
        # Arrange
        render_args = render_jwa_file_with_images_config_args

        # Build the expected results
        expected = copy.deepcopy(render_args)

        harness.begin()

        # Act
        actual_content_yaml = harness.charm._render_jwa_spawner_inputs(**render_args)
        actual_content = yaml.safe_load(actual_content_yaml)

        # Assert
        assert (
            actual_content["spawnerFormDefaults"]["image"]["value"]
            == expected["jupyter_images_config"].default
        )
        assert (
            actual_content["spawnerFormDefaults"]["image"]["options"]
            == expected["jupyter_images_config"].options
        )

        assert (
            actual_content["spawnerFormDefaults"]["imageGroupOne"]["value"]
            == expected["vscode_images_config"].default
        )
        assert (
            actual_content["spawnerFormDefaults"]["imageGroupOne"]["options"]
            == expected["vscode_images_config"].options
        )

        assert (
            actual_content["spawnerFormDefaults"]["imageGroupTwo"]["value"]
            == expected["rstudio_images_config"].default
        )
        assert (
            actual_content["spawnerFormDefaults"]["imageGroupTwo"]["options"]
            == expected["rstudio_images_config"].options
        )

        assert (
            actual_content["spawnerFormDefaults"]["gpus"]["value"]["vendor"]
            == expected["gpu_vendors_config"].default
        )
        assert (
            actual_content["spawnerFormDefaults"]["gpus"]["value"]["num"]
            == expected["gpu_number_default"]
        )
        assert (
            actual_content["spawnerFormDefaults"]["gpus"]["value"]["vendors"]
            == expected["gpu_vendors_config"].options
        )

        assert (
            actual_content["spawnerFormDefaults"]["affinityConfig"]["value"]
            == expected["affinity_options_config"].default
        )
        assert (
            actual_content["spawnerFormDefaults"]["affinityConfig"]["options"]
            == expected["affinity_options_config"].options
        )

        assert (
            actual_content["spawnerFormDefaults"]["tolerationGroup"]["value"]
            == expected["tolerations_options_config"].default
        )
        assert (
            actual_content["spawnerFormDefaults"]["tolerationGroup"]["options"]
            == expected["tolerations_options_config"].options
        )

        assert (
            actual_content["spawnerFormDefaults"]["configurations"]["value"]
            == expected["default_poddefaults_config"].options
        )

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_upload_jwa_file(self, k8s_resource_handler: MagicMock, harness: Harness):
        """Tests uploading the jwa config file to the container with the right contents."""
        # Arrange
        harness.begin()
        test_config = {"config": "test"}
        test_config_yaml = yaml.dump(test_config)
        harness.charm._upload_jwa_file_to_container(test_config_yaml)

        # Act
        actual_config = yaml.safe_load(
            harness.charm.container.pull("/etc/config/spawner_ui_config.yaml")
        )

        # Assert
        assert actual_config == test_config

    @pytest.mark.parametrize(
        "config_key, yaml_string",
        (
            ("jupyter-images", "{ not valid yaml"),
            ("vscode-images", "{ not valid yaml"),
            ("rstudio-images", "{ not valid yaml"),
            ("jupyter-images", "A string"),
            ("jupyter-images", "{}"),
        ),
    )
    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_failure_get_config(
        self, k8s_resource_handler: MagicMock, harness: Harness, config_key, yaml_string
    ):
        """Tests that an exception is raised when Notebook images config contains invalid input."""
        # Arrange
        harness.update_config({config_key: yaml_string})
        harness.begin()
        harness.charm.logger = MagicMock()

        # Act
        harness.charm._get_from_config(config_key)

        # Assert
        harness.charm.logger.warning.assert_called_once()

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    @patch("charm.JupyterUI.k8s_resource_handler")
    def test_sidecar_and_ambient_relations_added(
        self, k8s_resource_handler: MagicMock, harness: Harness
    ):
        """Test the charm is in BlockedStatus when both sidecar and ambient relations are added."""
        # Arrange
        harness.add_relation(INGRESS_ENDPOINT, ISTIO_PILOT_APP)

        harness.add_relation(ISTIO_INGRESS_ROUTE_ENDPOINT, ISTIO_INGRESS_K8S_APP)

        harness.add_storage("config")
        harness.add_storage("logos")
        # Act
        harness.begin_with_initial_hooks()

        # Assert
        assert isinstance(
            harness.charm.model.unit.status,
            BlockedStatus,
        )
