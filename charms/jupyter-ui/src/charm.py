#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#

"""A Juju Charm for Jupyter UI."""

import logging
from pathlib import Path

import yaml
from charmed_kubeflow_chisme.exceptions import ErrorWithStatus
from charmed_kubeflow_chisme.kubernetes import KubernetesResourceHandler
from charmed_kubeflow_chisme.lightkube.batch import delete_many
from charms.observability_libs.v1.kubernetes_service_patch import KubernetesServicePatch
from lightkube import ApiError
from lightkube.generic_resource import load_in_cluster_generic_resources
from lightkube.models.core_v1 import ServicePort
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ChangeError, Layer
from serialized_data_interface import NoCompatibleVersions, NoVersionsListed, get_interfaces

K8S_RESOURCE_FILES = [
    "src/templates/auth_manifests.yaml.j2",
]


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
        self._container = self.unit.get_container(self._name)

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

        # setup events
        for event in [
            self.on.leader_elected,
            self.on.upgrade_charm,
            self.on.config_changed,
            self.on["ingress"].relation_changed,
            self.on.jupyter_ui_pebble_ready,
        ]:
            self.framework.observe(event, self.main)
        self.framework.observe(self.on.jupyter_ui_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.remove, self._on_remove)

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
                    "override": "replace",
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

    def _upload_files_to_container(self):
        """Upload required files to container."""
        self.container.push(
            "/etc/config/spawner_ui_config.yaml",
            "spawner_ui_config.yaml",
            make_dirs=True,
        )
        for file_name, file_content in yaml.safe_load(
            Path("src/logos-configmap.yaml").read_text()
        )["data"].items():
            logo_file = "/src/apps/default/static/assets/logos/" + file_name
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

        # upload files to container
        self._upload_files_to_container()

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
        if interfaces["ingress"]:
            interfaces["ingress"].send_data(
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

    def main(self, _) -> None:
        """Perform all required actions of the Charm."""
        try:
            self._check_leader()
            self._deploy_k8s_resources()
            interfaces = self._get_interfaces()
            if self._is_container_ready():
                self._update_layer()
        except CheckFailed as err:
            self.model.unit.status = err.status
            return

        self._configure_mesh(interfaces)

        self.model.unit.status = ActiveStatus()


#
# Start main
#
if __name__ == "__main__":
    main(JupyterUI)
