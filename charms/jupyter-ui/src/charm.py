#!/usr/bin/env python3

import logging
from pathlib import Path

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from serialized_data_interface import NoCompatibleVersions, NoVersionsListed, get_interfaces

from oci_image import OCIImageResource, OCIImageResourceError

log = logging.getLogger()


class Operator(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)

        if not self.model.unit.is_leader():
            log.info("Not a leader, skipping set_pod_spec")
            self.model.unit.status = ActiveStatus()
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

        self.image = OCIImageResource(self, "oci-image")

        self.framework.observe(self.on.install, self.set_pod_spec)
        self.framework.observe(self.on.upgrade_charm, self.set_pod_spec)
        self.framework.observe(self.on.config_changed, self.set_pod_spec)

        self.framework.observe(self.on.install, self.send_info)
        self.framework.observe(self.on.upgrade_charm, self.send_info)
        self.framework.observe(self.on.config_changed, self.send_info)
        self.framework.observe(self.on['ingress'].relation_changed, self.send_info)

    def send_info(self, event):
        if self.interfaces["ingress"]:
            self.interfaces["ingress"].send_data(
                {
                    "prefix": '/jupyter/',
                    "service": self.model.app.name,
                    "port": self.model.config['port'],
                }
            )

    def set_pod_spec(self, event):
        try:
            image_details = self.image.fetch()
        except OCIImageResourceError as e:
            self.model.unit.status = e.status
            log.info(e)
            return

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
                            'USERID_HEADER': 'kubeflow-userid',
                            'USERID_PREFIX': '',
                            'UI': config['ui'],
                            'URL_PREFIX': config['url-prefix'],
                            'DEV_MODE': config['dev-mode'],
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
                        ],
                    }
                ],
            },
        )
        self.model.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(Operator)
