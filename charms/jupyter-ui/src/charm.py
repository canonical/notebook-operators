#!/usr/bin/env python3

import logging
from pathlib import Path

import yaml
from oci_image import OCIImageResource, OCIImageResourceError
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from serialized_data_interface import (
    NoCompatibleVersions,
    NoVersionsListed,
    get_interfaces,
)


class CheckFailed(Exception):
    """Raise this exception if one of the checks in main fails."""

    def __init__(self, msg, status_type=None):
        super().__init__()

        self.msg = msg
        self.status_type = status_type
        self.status = status_type(msg)


class Operator(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)

        self.log = logging.getLogger(__name__)

        self.image = OCIImageResource(self, "oci-image")
        for event in [
            self.on.install,
            self.on.leader_elected,
            self.on.upgrade_charm,
            self.on.config_changed,
            self.on['ingress'].relation_changed,
        ]:
            self.framework.observe(event, self.main)

    def main(self, event):
        try:
            self._check_leader()
            interfaces = self._get_interfaces()
            image_details = self._check_image_details()
        except CheckFailed as check_failed:
            self.model.unit.status = check_failed.status
            return

        self._configure_mesh(interfaces)
        config = self.model.config

        self.model.unit.status = MaintenanceStatus("Setting pod spec")
        self.model.pod.set_spec(
            {
                "version": 3,
                "serviceAccount": {
                    "roles": [
                        {
                            "global": True,
                            "rules": [
                                {
                                    'apiGroups': [''],
                                    'resources': ['namespaces'],
                                    'verbs': ['get', 'list', 'create', 'delete'],
                                },
                                {
                                    'apiGroups': ['authorization.k8s.io'],
                                    'resources': ['subjectaccessreviews'],
                                    'verbs': ['create'],
                                },
                                {
                                    'apiGroups': ['kubeflow.org'],
                                    'resources': [
                                        'notebooks',
                                        'notebooks/finalizers',
                                        'poddefaults',
                                    ],
                                    'verbs': ['get', 'list', 'create', 'delete', 'patch', 'update'],
                                },
                                {
                                    'apiGroups': [''],
                                    'resources': ['persistentvolumeclaims'],
                                    'verbs': ['create', 'delete', 'get', 'list'],
                                },
                                {
                                    'apiGroups': [''],
                                    'resources': ['events', 'nodes'],
                                    'verbs': ['list'],
                                },
                                {
                                    'apiGroups': ['storage.k8s.io'],
                                    'resources': ['storageclasses'],
                                    'verbs': ['get', 'list', 'watch'],
                                },
                            ],
                        }
                    ]
                },
                "containers": [
                    {
                        "name": "jupyter-ui",
                        "imageDetails": image_details,
                        'ports': [{'name': 'http', 'containerPort': config['port']}],
                        "envConfig": {
                            'APP_PREFIX': config['url-prefix'],
                            'APP_SECURE_COOKIES': str(config['secure-cookies']),
                            'BACKEND_MODE': config['backend-mode'],
                            'CLUSTER_DOMAIN': 'cluster.local',
                            'UI': config['ui'],
                            'USERID_HEADER': 'kubeflow-userid',
                            'USERID_PREFIX': '',
                        },
                        "volumeConfig": [
                            {
                                "name": "config",
                                "mountPath": "/etc/config",
                                "files": [
                                    {
                                        "path": "spawner_ui_config.yaml",
                                        "content": Path('src/spawner_ui_config.yaml').read_text(),
                                    }
                                ],
                            },
                            {
                                "name": "logos",
                                "mountPath": "/src/apps/default/static/assets/logos",
                                "files": [
                                    {
                                        "path": name,
                                        "content": content,
                                    }
                                    for name, content in yaml.safe_load(
                                        Path('src/logos-configmap.yaml').read_text()
                                    )['data'].items()
                                ],
                            },
                        ],
                    }
                ],
            },
        )
        self.model.unit.status = ActiveStatus()

    def _configure_mesh(self, interfaces):
        if interfaces["ingress"]:
            interfaces["ingress"].send_data(
                {
                    "prefix": self.model.config['url-prefix'] + '/',
                    "rewrite": "/",
                    "service": self.model.app.name,
                    "port": self.model.config["port"],
                }
            )

    def _check_leader(self):
        if not self.unit.is_leader():
            # We can't do anything useful when not the leader, so do nothing.
            raise CheckFailed("Waiting for leadership", WaitingStatus)

    def _get_interfaces(self):
        try:
            interfaces = get_interfaces(self)
        except NoVersionsListed as err:
            raise CheckFailed(str(err), WaitingStatus)
        except NoCompatibleVersions as err:
            raise CheckFailed(str(err), BlockedStatus)
        return interfaces

    def _check_image_details(self):
        try:
            image_details = self.image.fetch()
        except OCIImageResourceError as e:
            raise CheckFailed(f"{e.status_message}: oci-image", e.status_type)
        return image_details


if __name__ == "__main__":
    main(Operator)
