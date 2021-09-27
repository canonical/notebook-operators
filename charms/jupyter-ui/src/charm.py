#!/usr/bin/env python3

import logging
import urllib
import os
import yaml

from ops.charm import CharmBase
from ops.main import main
from kubernetes import kubernetes
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from serialized_data_interface import NoCompatibleVersions, NoVersionsListed, get_interfaces

from pathlib import Path

import resources

logger = logging.getLogger(__name__)


class JupyterUICharm(CharmBase):
    _authed = False
    """Charm the service."""
    def __init__(self, *args):
        super().__init__(*args)

        if not self.model.unit.is_leader():
            log.info("Not a leader, skipping set_pod_spec")
            self.model.unit.status = WaitingStatus("Waiting for leadership")
            return

        try:
            self.interfaces = get_interfaces(self)
        except NoVersionsListed as err:
            self.model.unit.status = WaitingStatus(str(err))
            return
        except NoCompatibleVersions as err:
            self.model.unit.status = BlockedStatus(str(err))
            return
        else:
            self.model.unit.status = ActiveStatus()

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.remove, self._on_remove)

        self.framework.observe(self.on.install, self.send_info)
        self.framework.observe(self.on.upgrade_charm, self.send_info)
        self.framework.observe(self.on.config_changed, self.send_info)
        self.framework.observe(self.on['ingress'].relation_changed, self.send_info)

    def send_info(self, event):
        if self.interfaces["ingress"]:
            self.interfaces["ingress"].send_data(
                {
                    "prefix": self.model.config['url-prefix'] + '/',
                    "rewrite": "/",
                    "service": self.model.app.name,
                    "port": self.model.config['port'],
                }
            )

    def _on_install(self, _):
        """Handle the install event, create Kubernetes resources"""
        logging.info("INSTALLING ......")
        if not self._k8s_auth():
            event.defer()
            return
        self.unit.status = MaintenanceStatus("creating k8s resources")
        # Create the Kubernetes resources needed for the Dashboard
        r = resources.JupyterUIResources(self)
        r.apply()

    def _on_remove(self, event):
        """Cleanup Kubernetes resources"""
        # Authenticate with the Kubernetes API
        if not self._k8s_auth():
            event.defer()
            return
        # Remove created Kubernetes resources
        r = resources.JupyterUIResources(self)
        r.delete()

    def _on_config_changed(self, event):
        # Defer the config-changed event if we do not have sufficient privileges
        if not self._k8s_auth():
            event.defer()
            return
        try:
            self._config_ui()
        except ConnectionError:
            logger.info("pebble socket not available, deferring config-changed")
            event.defer()
            return
        self.unit.status = ActiveStatus()

    def _config_ui(self):
        """Configure Pebble to start the Jupyter ui"""
        # Define a simple layer
        config = self.model.config
        layer = {
            "services": {"jupyter-ui":
                            {
                                "override": "replace",
                                "startup": "enabled",
                                "command": "python3 main.py",
                                "environment": {
                                    'USERID_HEADER': 'kubeflow-userid',
                                    'USERID_PREFIX': '',
                                    'UI': config['ui'],
                                    'URL_PREFIX': config['url-prefix'],
                                    'DEV_MODE': config['dev-mode'],
                                },
                            }
                        },
                }
        config_template = None
        with open(Path('src/spawner_ui_config.yaml')) as file:
            config_template = yaml.full_load(file)
        # Configure jupyter notebook url list
        if config['default_notebook_lists'] != "default":
            config_template['spawnerFormDefaults']['image']['options'] = \
                                            config['default_notebook_lists'].split(',')
            config_template['spawnerFormDefaults']['image']['value'] = \
                                            config['default_notebook_lists'].split(',')[0]
        # Add a Pebble config layer to the scraper container
        container = self.unit.get_container("jupyter-ui")
        container.push("/etc/config/spawner_ui_config.yaml", yaml.dump(config_template))
        container.add_layer("jupyter-ui", layer, combine=True)
        # Check if the scraper service is already running and start it if not
        if not container.get_service("jupyter-ui").is_running():
            container.start("jupyter-ui")
            logger.info("Jupyter-ui service started")

    def _k8s_auth(self) -> bool:
        """Authenticate to kubernetes."""
        if self._authed:
            return True
        # Remove os.environ.update when lp:1892255 is FIX_RELEASED.
        os.environ.update(
            dict(
                e.split("=")
                for e in Path("/proc/1/environ").read_text().split("\x00")
                if "KUBERNETES_SERVICE" in e
            )
        )
        # Authenticate against the Kubernetes API using a mounted ServiceAccount token
        kubernetes.config.load_incluster_config()
        # Test the service account we've got for sufficient perms
        auth_api = kubernetes.client.RbacAuthorizationV1Api(kubernetes.client.ApiClient())

        try:
            auth_api.list_cluster_role()
        except kubernetes.client.exceptions.ApiException as e:
            if e.status == 403:
                # If we can't read a cluster role, we don't have enough permissions
                self.unit.status = BlockedStatus("Run juju trust on this application to continue")
                return False
            else:
                raise e

        self._authed = True
        return True

if __name__ == "__main__":
    main(JupyterUICharm)