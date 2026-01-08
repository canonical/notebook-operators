#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Juju Charm for Jupyter UI."""

import logging
from pathlib import Path
from typing import Union

import yaml
from charmed_kubeflow_chisme.exceptions import ErrorWithStatus
from charmed_kubeflow_chisme.kubernetes import KubernetesResourceHandler
from charmed_kubeflow_chisme.lightkube.batch import delete_many
from charms.istio_beacon_k8s.v0.service_mesh import ServiceMeshConsumer
from charms.istio_ingress_k8s.v0.istio_ingress_route import (
    BackendRef,
    HTTPPathMatch,
    HTTPPathMatchType,
    HTTPRoute,
    HTTPRouteMatch,
    IstioIngressRouteConfig,
    IstioIngressRouteRequirer,
    Listener,
    PathModifier,
    PathModifierType,
    ProtocolType,
    URLRewriteFilter,
    URLRewriteSpec,
)
from charms.kubeflow_dashboard.v0.kubeflow_dashboard_links import (
    DashboardLink,
    KubeflowDashboardLinksRequirer,
)
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.observability_libs.v1.kubernetes_service_patch import KubernetesServicePatch
from jinja2 import Environment, FileSystemLoader
from lightkube import ApiError
from lightkube.generic_resource import load_in_cluster_generic_resources
from lightkube.models.core_v1 import ServicePort
from ops import main
from ops.charm import CharmBase
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ChangeError, Layer
from serialized_data_interface import NoCompatibleVersions, NoVersionsListed, get_interfaces
from yaml import YAMLError
from yaml.parser import ParserError

from config_validators import (
    ConfigValidationError,
    OptionsWithDefault,
    parse_gpu_num,
    validate_named_options_with_default,
)

K8S_RESOURCE_FILES = [
    "src/templates/auth_manifests.yaml.j2",
]
INGRESS_RELATION = "ingress"
ISTIO_INGRESS_ROUTE_RELATION = "istio-ingress-route"
JUPYTER_IMAGES_CONFIG = "jupyter-images"
VSCODE_IMAGES_CONFIG = "vscode-images"
RSTUDIO_IMAGES_CONFIG = "rstudio-images"
GPU_NUMBER_CONFIG = "gpu-number-default"
GPU_VENDORS_CONFIG = "gpu-vendors"
GPU_VENDORS_CONFIG_DEFAULT = f"{GPU_VENDORS_CONFIG}-default"
AFFINITY_OPTIONS_CONFIG = "affinity-options"
AFFINITY_OPTIONS_CONFIG_DEFAULT = f"{AFFINITY_OPTIONS_CONFIG}-default"
TOLERATIONS_OPTIONS_CONFIG = "tolerations-options"
TOLERATIONS_OPTIONS_CONFIG_DEFAULT = f"{TOLERATIONS_OPTIONS_CONFIG}-default"
DEFAULT_PODDEFAULTS_CONFIG = "default-poddefaults"
JWA_CONFIG_FILE = "src/templates/spawner_ui_config.yaml.j2"
JWA_CONFIG_FILE_DST = "spawner_ui_config.yaml"

IMAGE_CONFIGS = [
    JUPYTER_IMAGES_CONFIG,
    VSCODE_IMAGES_CONFIG,
    RSTUDIO_IMAGES_CONFIG,
]
DEFAULT_WITH_OPTIONS_CONFIGS = [
    GPU_VENDORS_CONFIG,
    TOLERATIONS_OPTIONS_CONFIG,
    AFFINITY_OPTIONS_CONFIG,
]

DEFAULT_JUPYTER_IMAGES_FILE = "src/default-jupyter-images.yaml"
DEFAULT_RSTUDIO_IMAGES_FILE = "src/default-rstudio-images.yaml"
DEFAULT_VSCODE_IMAGES_FILE = "src/default-vscode-images.yaml"


class CheckFailed(Exception):
    """Raise this exception if one of the checks in main fails."""

    def __init__(self, msg, status_type=None):
        """Raise this exception if one of the checks in main fails."""
        super().__init__()

        self.msg = msg
        self.status_type = status_type
        self.status = status_type(msg)


class JupyterUI(CharmBase):
    """A Juju Charm for Jupyter UI."""

    def __init__(self, *args):
        """Initialize charm and setup the container."""
        super().__init__(*args)

        # retrieve configuration and base settings
        self.logger = logging.getLogger(__name__)
        self._namespace = self.model.name
        self._lightkube_field_manager = "lightkube"
        self._name = self.model.app.name
        self._http_port = self.model.config["port"]
        self._exec_command = (
            "gunicorn"
            " -w 3"
            f" --bind 0.0.0.0:{self._http_port}"
            " --access-logfile"
            " - entrypoint:app"
        )
        self._container_name = "jupyter-ui"
        self._container_meta = self.meta.containers[self._container_name]
        self._container = self.unit.get_container(self._name)
        self._config_storage_name = "config"
        self._logos_storage_name = "logos"
        self._container_meta = self.meta.containers[self._container_name]

        # setup context to be used for updating K8S resources
        self._context = {
            "app_name": self._name,
            "namespace": self._namespace,
            "service": self._name,
        }
        self._k8s_resource_handler = None

        http_port = ServicePort(int(self._http_port), name="http")
        self.service_patcher = KubernetesServicePatch(
            self, [http_port], service_name=f"{self.model.app.name}"
        )

        self.ingress = IstioIngressRouteRequirer(
            self,
            relation_name=ISTIO_INGRESS_ROUTE_RELATION,
        )

        self._configure_ambient_ingress()

        self._mesh = ServiceMeshConsumer(self)

        # setup events
        for event in [
            self.on.leader_elected,
            self.on.upgrade_charm,
            self.on.config_changed,
            self.on[INGRESS_RELATION].relation_changed,
            self.on[ISTIO_INGRESS_ROUTE_RELATION].relation_changed,
        ]:
            self.framework.observe(event, self.main)
        self.framework.observe(self.on.jupyter_ui_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.remove, self._on_remove)

        # add link to notebook in kubeflow-dashboard sidebar
        self.kubeflow_dashboard_sidebar = KubeflowDashboardLinksRequirer(
            charm=self,
            relation_name="dashboard-links",
            dashboard_links=[
                DashboardLink(
                    type="item",
                    link="/jupyter/",
                    text="Notebooks",
                    icon="book",
                    location="menu",
                )
            ],
        )
        self._logging = LogForwarder(charm=self)

    def _configure_ambient_ingress(self):
        """Configure Istio Ambient Mesh ingress routing for the Jupyter UI service.

        Creates and submits an IstioIngressRouteConfig that defines:
        - HTTP listener on port 80
        - Path-based routing matching requests with /jupyter prefix
        - Backend routing to the jupyter-ui service
        """
        # Define listeners - names are auto-generated by the charm
        http_listener = Listener(port=80, protocol=ProtocolType.HTTP)

        config = IstioIngressRouteConfig(
            model=self.model.name,  # Requirer's namespace where services live
            listeners=[http_listener],
            http_routes=[
                HTTPRoute(
                    name="http-route",
                    listener=http_listener,
                    matches=[
                        HTTPRouteMatch(
                            path=HTTPPathMatch(
                                type=HTTPPathMatchType.PathPrefix, value="/jupyter/"
                            ),
                        )
                    ],
                    filters=[
                        URLRewriteFilter(
                            urlRewrite=URLRewriteSpec(
                                path=PathModifier(
                                    type=PathModifierType.ReplacePrefixMatch, value="/"
                                )
                            )
                        )
                    ],
                    backends=[BackendRef(service=self.app.name, port=self.model.config["port"])],
                ),
            ],
        )
        # Only submit config if we are a leader
        if self.unit.is_leader():
            self.ingress.submit_config(config)

    @property
    def container(self):
        """Return container."""
        return self._container

    @property
    def k8s_resource_handler(self):
        """Update K8S with K8S resources."""
        if not self._k8s_resource_handler:
            self._k8s_resource_handler = KubernetesResourceHandler(
                field_manager=self._lightkube_field_manager,
                template_files=K8S_RESOURCE_FILES,
                context=self._context,
                logger=self.logger,
            )
        load_in_cluster_generic_resources(self._k8s_resource_handler.lightkube_client)
        return self._k8s_resource_handler

    @k8s_resource_handler.setter
    def k8s_resource_handler(self, handler: KubernetesResourceHandler):
        self._k8s_resource_handler = handler

    def _get_env_vars(self):
        """Return environment variables based on model configuration."""
        config = self.model.config
        ret_env_vars = {
            "APP_PREFIX": config["url-prefix"],
            "APP_SECURE_COOKIES": str(config["secure-cookies"]),
            "BACKEND_MODE": config["backend-mode"],
            "CLUSTER_DOMAIN": "cluster.local",
            "UI": config["ui"],
            "USERID_HEADER": "kubeflow-userid",
            "USERID_PREFIX": "",
        }

        return ret_env_vars

    @property
    def _jupyter_ui_layer(self) -> Layer:
        """Create and return Pebble framework layer."""
        # fetch environment
        env_vars = self._get_env_vars()

        layer_config = {
            "summary": "jupyter-ui layer",
            "description": "Pebble config layer for jupyter-ui",
            "services": {
                self._container_name: {
                    "override": "merge",
                    "summary": "Entrypoint of jupyter-ui image",
                    "command": self._exec_command,
                    "startup": "enabled",
                    "environment": env_vars,
                    "on-check-failure": {"up": "restart"},
                }
            },
            "checks": {
                "up": {
                    "override": "replace",
                    "period": "30s",
                    "http": {"url": f"http://localhost:{self._http_port}"},
                },
            },
        }

        return Layer(layer_config)

    def _update_layer(self) -> None:
        """Update the Pebble configuration layer (if changed)."""
        current_layer = self.container.get_plan()
        new_layer = self._jupyter_ui_layer
        if current_layer.services != new_layer.services:
            self.unit.status = MaintenanceStatus("Applying new pebble layer")
            self.container.add_layer(self._container_name, new_layer, combine=True)
            try:
                self.logger.info("Pebble plan updated with new configuration, replaning")
                self.container.replan()
            except ChangeError:
                raise ErrorWithStatus("Failed to replan", BlockedStatus)

    def _upload_logos_files_to_container(self):
        """Upload logos files to container.

        Parses the logos-configmap.yaml file,
        splits it into files as expected by the workload,
        and pushes the files to the container.
        """
        logos_storage_path = Path(self._container_meta.mounts[self._logos_storage_name].location)
        for file_name, file_content in yaml.safe_load(
            Path("src/logos-configmap.yaml").read_text()
        )["data"].items():
            logo_file = logos_storage_path / file_name
            self.container.push(
                logo_file,
                file_content,
                make_dirs=True,
            )

    def _deploy_k8s_resources(self) -> None:
        """Deploys K8S resources."""
        try:
            self.unit.status = MaintenanceStatus("Creating K8S resources")
            self.k8s_resource_handler.apply()
        except ApiError:
            raise ErrorWithStatus("K8S resources creation failed", BlockedStatus)
        self.model.unit.status = MaintenanceStatus("K8S resources created")

    def _get_images_config(self, key: str) -> OptionsWithDefault:
        """Load, validate, render and return the config value for Notebook Images.

        The config options for the notebook images will have an empty value by default.
        Thus the default value will be read from the corresponding files with the default
        values.
        """
        default_images_file = ""
        if key == JUPYTER_IMAGES_CONFIG:
            default_images_file = DEFAULT_JUPYTER_IMAGES_FILE
        if key == RSTUDIO_IMAGES_CONFIG:
            default_images_file = DEFAULT_RSTUDIO_IMAGES_FILE
        if key == VSCODE_IMAGES_CONFIG:
            default_images_file = DEFAULT_VSCODE_IMAGES_FILE

        try:
            images = yaml.safe_load(str(self.model.config.get(key, "")))
            self.logger.info(f"Model config value: {self.model.config.get(key, '')}")
        except ParserError as e:
            self.logger.warning(f"Config value is not a yaml for {key}: {e}")
            return OptionsWithDefault()

        # Config value is not changed, need to use the default images list
        if images is None:
            self.logger.info(f"No images in the config {key}. Will use default values.")
            images = yaml.safe_load(Path(default_images_file).read_text())

        if not isinstance(images, list):
            self.logger.warning(f"Config for {key} is not a yaml list: {images}")
            return OptionsWithDefault()

        # user explicitly asked for no images
        if images == []:
            self.logger.info(f"Config for {key} has empty list. Will not set any images")
            return OptionsWithDefault(default="", options=[])

        return OptionsWithDefault(default=images[0], options=images)

    def _get_from_config(self, key) -> Union[OptionsWithDefault, str]:
        """Load, validate, render, and return the config value stored in self.model.config[key].

        Different keys are parsed and validated differently.  Errors parsing a config result in
        null values being returned and errors being logged - this should not raise an exception on
        invalid input.
        """
        if key in IMAGE_CONFIGS:
            return self._get_images_config(key)
        elif key in DEFAULT_WITH_OPTIONS_CONFIGS:
            return self._get_options_with_default_from_config(key)
        elif key == DEFAULT_PODDEFAULTS_CONFIG:
            # parsed the same as image configs
            return self._get_list_config(key)
        elif key == GPU_NUMBER_CONFIG:
            return parse_gpu_num(self.model.config[key])
        else:
            return self.model.config[key]

    def _get_list_config(self, key) -> OptionsWithDefault:
        """Parse and return a config entry which should render to a list, like the image lists.

        Returns a OptionsWithDefault with:
            .options: the content of the config
            .default: the first element of the list
        """
        error_message = f"Cannot parse list input from config '{key}` - ignoring this input."
        try:
            options = yaml.safe_load(self.model.config[key])

            # Empty yaml string, which resolves to None, should be treated as an empty list
            if options is None:
                options = []

            # Check that we receive a list or tuple.  This filters out types that can be indexed but
            # are not valid for this config (like strings or dicts).
            if not isinstance(options, (tuple, list)):
                self.logger.warning(
                    f"{error_message}  Input must be a list or empty string. Got: '{options}'"
                )
                return OptionsWithDefault()

            if len(options) > 0:
                default = options[0]
            else:
                default = ""

            return OptionsWithDefault(default=default, options=options)
        except yaml.YAMLError as err:
            self.logger.warning(f"{error_message}  Got error: {err}")
            return OptionsWithDefault()

    def _get_options_with_default_from_config(self, key) -> OptionsWithDefault:
        """Return the input config for a config specified by a list of options and their default.

        This is for options like the affinity, gpu, or tolerations options which consist of a list
        of options dicts and a separate config specifying their default value.

        This function handles any config parsing or validation errors, logging details and returning
        and empty result in case of errors.

        Returns a OptionsWithDefault with:
            .options: the content of this config
            .default: the option selected by f'{key}-default'
        """
        default_key = f"{key}-default"
        try:
            default = self.model.config[default_key]
            options = self.model.config[key]
            options = yaml.safe_load(options)
            # Convert anything empty to an empty list
            if not options:
                options = []
            validate_named_options_with_default(default, options, name=key)
            return OptionsWithDefault(default=default, options=options)
        except (YAMLError, ConfigValidationError) as e:
            self.logger.warning(f"Failed to parse {key} config:\n{e}")
            return OptionsWithDefault()

    @staticmethod
    def _render_jwa_spawner_inputs(
        jupyter_images_config: OptionsWithDefault,
        vscode_images_config: OptionsWithDefault,
        rstudio_images_config: OptionsWithDefault,
        gpu_number_default: str,
        gpu_vendors_config: OptionsWithDefault,
        affinity_options_config: OptionsWithDefault,
        tolerations_options_config: OptionsWithDefault,
        default_poddefaults_config: OptionsWithDefault,
    ):
        """Render the JWA configmap template with the user-set images in the juju config."""
        environment = Environment(loader=FileSystemLoader("."))
        # Add a filter to render yaml with proper formatting
        environment.filters["to_yaml"] = _to_yaml
        template = environment.get_template(JWA_CONFIG_FILE)
        content = template.render(
            jupyter_images=jupyter_images_config.options,
            jupyter_images_default=jupyter_images_config.default,
            vscode_images=vscode_images_config.options,
            vscode_images_default=vscode_images_config.default,
            rstudio_images=rstudio_images_config.options,
            rstudio_images_default=rstudio_images_config.default,
            gpu_number_default=gpu_number_default,
            gpu_vendors=gpu_vendors_config.options,
            gpu_vendors_default=gpu_vendors_config.default,
            affinity_options=affinity_options_config.options,
            affinity_options_default=affinity_options_config.default,
            tolerations_options=tolerations_options_config.options,
            tolerations_options_default=tolerations_options_config.default,
            default_poddefaults=default_poddefaults_config.options,
        )
        return content

    def _upload_jwa_file_to_container(self, file_content):
        """Pushes the JWA spawner config file to the workload container."""
        config_storage_path = Path(self._container_meta.mounts[self._config_storage_name].location)
        self.container.push(
            config_storage_path / JWA_CONFIG_FILE_DST,
            file_content,
            make_dirs=True,
        )

    def _update_spawner_ui_config(self):
        """Update the images options that can be selected in the dropdown list."""
        # get config
        jupyter_images_config = self._get_from_config(JUPYTER_IMAGES_CONFIG)
        vscode_images_config = self._get_from_config(VSCODE_IMAGES_CONFIG)
        rstusio_images_config = self._get_from_config(RSTUDIO_IMAGES_CONFIG)
        gpu_number_default = self._get_from_config(GPU_NUMBER_CONFIG)
        gpu_vendors_config = self._get_from_config(GPU_VENDORS_CONFIG)
        affinity_options_config = self._get_from_config(AFFINITY_OPTIONS_CONFIG)
        tolerations_options_config = self._get_from_config(TOLERATIONS_OPTIONS_CONFIG)
        default_poddefaults = self._get_from_config(DEFAULT_PODDEFAULTS_CONFIG)
        # render the jwa file
        jwa_content = self._render_jwa_spawner_inputs(
            jupyter_images_config=jupyter_images_config,
            vscode_images_config=vscode_images_config,
            rstudio_images_config=rstusio_images_config,
            gpu_number_default=gpu_number_default,
            gpu_vendors_config=gpu_vendors_config,
            affinity_options_config=affinity_options_config,
            tolerations_options_config=tolerations_options_config,
            default_poddefaults_config=default_poddefaults,
        )
        # push file
        self._upload_jwa_file_to_container(jwa_content)

    def _on_install(self, _):
        """Perform installation only actions."""
        try:
            # deploy K8S resources to speed up deployment
            self._deploy_k8s_resources()
        except CheckFailed as err:
            self.model.unit.status = err.status
        return

    def _on_pebble_ready(self, _):
        """Configure started container."""
        if not self._is_container_ready():
            return

        try:
            self._check_storage()
        except CheckFailed as err:
            self.model.unit.status = err.status
            return
        # upload files to container
        self._upload_logos_files_to_container()

        # proceed with other actions
        self.main(_)

    def _on_remove(self, _):
        """Remove all resources."""
        self.unit.status = MaintenanceStatus("Removing K8S resources")
        k8s_resources_manifests = self.k8s_resource_handler.render_manifests()
        try:
            delete_many(self.k8s_resource_handler.lightkube_client, k8s_resources_manifests)
        except ApiError as e:
            self.logger.warning(f"Failed to delete K8S resources, with error: {e}")
            raise e
        self.unit.status = MaintenanceStatus("K8S resources removed")

    def _configure_mesh(self, interfaces):
        if interfaces[INGRESS_RELATION]:
            interfaces[INGRESS_RELATION].send_data(
                {
                    "prefix": self.model.config["url-prefix"] + "/",
                    "rewrite": "/",
                    "service": self.model.app.name,
                    "port": self.model.config["port"],
                }
            )

    def _is_container_ready(self):
        """Check if connection can be made with container.

        Returns: False if container is not available
                 True if connection can be made
        Sets maintenance status if container is not available.
        """
        if not self.container.can_connect():
            self.unit.status = MaintenanceStatus("Waiting for pod startup to complete")
            return False
        return True

    def _check_leader(self):
        """Check if this unit is a leader."""
        if not self.unit.is_leader():
            self.logger.info("Not a leader")
            raise CheckFailed("Waiting for leadership", WaitingStatus)

    def _get_interfaces(self):
        try:
            interfaces = get_interfaces(self)
        except NoVersionsListed as err:
            raise CheckFailed(str(err), WaitingStatus)
        except NoCompatibleVersions as err:
            raise CheckFailed(str(err), BlockedStatus)
        return interfaces

    def _check_istio_relations(self):
        """Check that both ambient and sidecar relations are not present simultaneously."""
        ambient_relation = self.model.get_relation(ISTIO_INGRESS_ROUTE_RELATION)
        sidecar_relation = self.model.get_relation(INGRESS_RELATION)

        if ambient_relation and sidecar_relation:
            self.logger.error(
                f"Both '{ISTIO_INGRESS_ROUTE_RELATION}' and '{INGRESS_RELATION}' "
                "relations are present, remove one to unblock."
            )
            raise CheckFailed(
                f"Cannot have both '{ISTIO_INGRESS_ROUTE_RELATION}' and '{INGRESS_RELATION}' "
                "relations at the same time.",
                BlockedStatus,
            )

    def _check_storage(self):
        """Check if storage is available."""
        config_storage_path = Path(self._container_meta.mounts[self._config_storage_name].location)
        logos_storage_path = Path(self._container_meta.mounts[self._logos_storage_name].location)

        if not self.container.exists(config_storage_path):
            self.logger.info('Storage "config" not yet available')
            raise CheckFailed('Waiting for "config" storage', WaitingStatus)
        if not self.container.exists(logos_storage_path):
            self.logger.info('Storage "logos" not yet available')
            raise CheckFailed('Waiting for "logos" storage', WaitingStatus)

    def main(self, _) -> None:
        """Perform all required actions of the Charm."""
        try:
            self._check_leader()
            self._deploy_k8s_resources()
            if self._is_container_ready():
                self._update_layer()
                self._update_spawner_ui_config()
                self._check_istio_relations()
                interfaces = self._get_interfaces()
                self._configure_mesh(interfaces)
        except CheckFailed as err:
            self.model.unit.status = err.status
            return

        self.model.unit.status = ActiveStatus()


def _to_yaml(data: str) -> str:
    """Jinja filter to convert data to formatted yaml.

    This is used in the jinja template to format the yaml in the template.
    """
    return yaml.safe_dump(data)


if __name__ == "__main__":
    main(JupyterUI)
