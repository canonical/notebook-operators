#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Charm for the jupyter notebook server.

https://github.com/canonical/notebook-operators
"""
import logging

from charmed_kubeflow_chisme.exceptions import ErrorWithStatus, GenericCharmRuntimeError
from charmed_kubeflow_chisme.kubernetes import KubernetesResourceHandler
from charmed_kubeflow_chisme.lightkube.batch import delete_many
from charmed_kubeflow_chisme.pebble import update_layer
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from lightkube import ApiError
from lightkube.generic_resource import load_in_cluster_generic_resources
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, ModelError, WaitingStatus
from ops.pebble import CheckStatus, Layer

METRICS_PORT = "8080"
METRICS_PATH = "/metrics"
PROBE_PORT = "8081"
PROBE_PATH = "/healthz"

K8S_RESOURCE_FILES = [
    "src/templates/auth_manifests.yaml.j2",
]
CRD_RESOURCE_FILES = [
    "src/templates/crds.yaml.j2",
]


class JupyterController(CharmBase):
    """Charm for the jupyter notebook server."""

    def __init__(self, *args):
        """Initialize charm and setup the container."""
        super().__init__(*args)

        # retrieve configuration and base settings
        self.logger = logging.getLogger(__name__)
        self._namespace = self.model.name
        self._lightkube_field_manager = "lightkube"
        self._name = self.model.app.name
        self._exec_command = "./manager"
        self._container_name = "jupyter-controller"
        self._container = self.unit.get_container(self._container_name)

        # setup context to be used for updating K8S resources
        self._context = {
            "app_name": self._name,
            "namespace": self._namespace,
            "service": self._name,
        }
        self._k8s_resource_handler = None
        self._crd_resource_handler = None

        # setup events to be handled by main event handler
        self.framework.observe(self.on.config_changed, self._on_event)
        self.framework.observe(self.on.jupyter_controller_pebble_ready, self._on_event)
        for rel in self.model.relations.keys():
            self.framework.observe(self.on[rel].relation_changed, self._on_event)

        # setup events to be handled by specific event handlers
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade)
        self.framework.observe(self.on.remove, self._on_remove)
        self.framework.observe(self.on.update_status, self._on_update_status)

        self.prometheus_provider = MetricsEndpointProvider(
            charm=self,
            relation_name="metrics-endpoint",
            jobs=[
                {
                    "metrics_path": METRICS_PATH,
                    "static_configs": [{"targets": ["*:{}".format(METRICS_PORT)]}],
                }
            ],
        )

        self.dashboard_provider = GrafanaDashboardProvider(self)

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

    @property
    def crd_resource_handler(self):
        """Update K8S with CRD resources."""
        if not self._crd_resource_handler:
            self._crd_resource_handler = KubernetesResourceHandler(
                field_manager=self._lightkube_field_manager,
                template_files=CRD_RESOURCE_FILES,
                context=self._context,
                logger=self.logger,
            )
        load_in_cluster_generic_resources(self._crd_resource_handler.lightkube_client)
        return self._crd_resource_handler

    @crd_resource_handler.setter
    def crd_resource_handler(self, handler: KubernetesResourceHandler):
        self._crd_resource_handler = handler

    @property
    def service_environment(self):
        """Return environment variables based on model configuration."""
        config = self.model.config
        ret_env_vars = {
            "USE_ISTIO": "true",
            "ISTIO_GATEWAY": f"{self.model.name}/kubeflow-gateway",
            "ENABLE_CULLING": config["enable-culling"],
        }

        return ret_env_vars

    @property
    def _jupyter_controller_layer(self) -> Layer:
        """Create and return Pebble framework layer."""
        layer_config = {
            "summary": "jupyter-controller layer",
            "description": "Pebble config layer for jupyter-controller",
            "services": {
                self._container_name: {
                    "override": "replace",
                    "summary": "Entrypoint of jupyter-controller image",
                    "command": self._exec_command,
                    "startup": "enabled",
                    "environment": self.service_environment,
                    "on-check-failure": {"jupyter-controller-up": "restart"},
                }
            },
            "checks": {
                "jupyter-controller-up": {
                    "override": "replace",
                    "period": "30s",
                    "timeout": "20s",
                    "threshold": 4,
                    "http": {"url": f"http://localhost:{PROBE_PORT}{PROBE_PATH}"},
                }
            },
        }

        return Layer(layer_config)

    def _check_leader(self):
        """Check if this unit is a leader."""
        if not self.unit.is_leader():
            self.logger.warning("Not a leader, skipping setup")
            raise ErrorWithStatus("Waiting for leadership", WaitingStatus)

    def _check_and_report_k8s_conflict(self, error):
        """Return True if error status code is 409 (conflict), False otherwise."""
        if error.status.code == 409:
            self.logger.warning(f"Encountered a conflict: {error}")
            return True
        return False

    def _apply_k8s_resources(self, force_conflicts: bool = False) -> None:
        """Apply K8S resources.

        Args:
            force_conflicts (bool): *(optional)* Will "force" apply requests causing conflicting
                                    fields to change ownership to the field manager used in this
                                    charm.
                                    NOTE: This will only be used if initial regular apply() fails.
        """
        self.unit.status = MaintenanceStatus("Creating K8S resources")
        try:
            self.k8s_resource_handler.apply()
        except ApiError as error:
            if self._check_and_report_k8s_conflict(error) and force_conflicts:
                # conflict detected when applying K8S resources
                # re-apply K8S resources with forced conflict resolution
                self.unit.status = MaintenanceStatus("Force applying K8S resources")
                self.logger.warning("Apply K8S resources with forced changes against conflicts")
                self.k8s_resource_handler.apply(force=force_conflicts)
            else:
                raise GenericCharmRuntimeError("K8S resources creation failed") from error
        try:
            self.crd_resource_handler.apply()
        except ApiError as error:
            if self._check_and_report_k8s_conflict(error) and force_conflicts:
                # conflict detected when applying CRD resources
                # re-apply CRD resources with forced conflict resolution
                self.unit.status = MaintenanceStatus("Force applying CRD resources")
                self.logger.warning("Apply CRD resources with forced changes against conflicts")
                self.crd_resource_handler.apply(force=force_conflicts)
            else:
                raise GenericCharmRuntimeError("CRD resources creation failed") from error
        self.model.unit.status = MaintenanceStatus("K8S resources created")

    def _check_container_connection(self):
        """Check if connection can be made with container."""
        if not self.container.can_connect():
            raise ErrorWithStatus("Pod startup is not complete", MaintenanceStatus)

    def _check_status(self):
        """Check status of workload and set status accordingly."""
        container = self.unit.get_container(self._container_name)
        try:
            check = container.get_check("jupyter-controller-up")
        except ModelError as error:
            raise GenericCharmRuntimeError(
                "Failed to run health check on workload container"
            ) from error
        if check.status != CheckStatus.UP:
            self.logger.error(
                f"Container {self._container_name} failed health check. It will be restarted."
            )
            raise ErrorWithStatus("Workload failed health check", MaintenanceStatus)
        else:
            self.model.unit.status = ActiveStatus()

    def _on_install(self, _):
        """Installation only tasks."""
        # deploy K8S resources to speed up deployment
        self._apply_k8s_resources()

    def _on_upgrade(self, _):
        """Perform upgrade steps."""
        # force conflict resolution in K8S resources update
        self._on_event(_, force_conflicts=True)

    def _on_remove(self, _):
        """Remove all resources."""
        delete_error = None
        self.unit.status = MaintenanceStatus("Removing K8S resources")
        k8s_resources_manifests = self.k8s_resource_handler.render_manifests()
        crd_resources_manifests = self.crd_resource_handler.render_manifests()
        try:
            delete_many(self.k8s_resource_handler.lightkube_client, k8s_resources_manifests)
        except ApiError as error:
            # do not log/report when resources were not found
            if error.status.code != 404:
                self.logger.error(f"Failed to delete CRD resources, with error: {error}")
                delete_error = error
        try:
            delete_many(self.crd_resource_handler.lightkube_client, crd_resources_manifests)
        except ApiError as error:
            # do not log/report when resources were not found
            if error.status.code != 404:
                self.logger.error(f"Failed to delete K8S resources, with error: {error}")
                delete_error = error

        if delete_error is not None:
            raise delete_error

        self.unit.status = MaintenanceStatus("K8S resources removed")

    def _on_update_status(self, _):
        """Update status actions."""
        self._on_event(_)
        self._check_status()

    def _on_event(self, event, force_conflicts: bool = False) -> None:
        """Perform all required actions for the Charm.

        Args:
            force_conflicts (bool): Should only be used when need to resolved conflicts on K8S
                                    resources.
        """
        try:
            self._check_container_connection()
            self._check_leader()
            self._apply_k8s_resources(force_conflicts=force_conflicts)
            update_layer(
                self._container_name,
                self._container,
                self._jupyter_controller_layer,
                self.logger,
            )
        except ErrorWithStatus as err:
            self.model.unit.status = err.status
            self.logger.error(f"Failed to handle {event} with error: {err}")
            return

        self.model.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(JupyterController)
