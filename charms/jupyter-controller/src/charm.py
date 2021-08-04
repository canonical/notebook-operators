#!/usr/bin/env python3

import logging
from pathlib import Path

import yaml
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus

from oci_image import OCIImageResource, OCIImageResourceError

log = logging.getLogger()


class Operator(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)

        if not self.model.unit.is_leader():
            log.info("Not a leader, skipping set_pod_spec")
            self.model.unit.status = WaitingStatus("Waiting for leadership")
            return

        self.image = OCIImageResource(self, "oci-image")

        self.framework.observe(self.on.install, self.set_pod_spec)
        self.framework.observe(self.on.upgrade_charm, self.set_pod_spec)
        self.framework.observe(self.on.config_changed, self.set_pod_spec)

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
                                    'apiGroups': ['apps'],
                                    'resources': ['statefulsets'],
                                    'verbs': ['*'],
                                },
                                {
                                    'apiGroups': [''],
                                    'resources': ['events'],
                                    'verbs': ['create', 'get', 'list', 'watch'],
                                },
                                {
                                    'apiGroups': [''],
                                    'resources': ['pods'],
                                    'verbs': ['get', 'list', 'watch'],
                                },
                                {'apiGroups': [''], 'resources': ['services'], 'verbs': ['*']},
                                {
                                    'apiGroups': ['kubeflow.org'],
                                    'resources': [
                                        'notebooks',
                                        'notebooks/finalizers',
                                        'notebooks/status',
                                    ],
                                    'verbs': ['*'],
                                },
                                {
                                    'apiGroups': ['networking.istio.io'],
                                    'resources': ['virtualservices'],
                                    'verbs': ['*'],
                                },
                            ],
                        }
                    ]
                },
                "containers": [
                    {
                        'name': 'jupyter-controller',
                        "imageDetails": image_details,
                        'command': ['./manager'],
                        'envConfig': {
                            'USE_ISTIO': 'true',
                            'ISTIO_GATEWAY': f'{self.model.name}/kubeflow-gateway',
                            'ENABLE_CULLING': config['enable-culling'],
                        },
                    }
                ],
            },
            k8s_resources={
                "kubernetesResources": {
                    "customResourceDefinitions": [
                        {"name": crd["metadata"]["name"], "spec": crd["spec"]}
                        for crd in yaml.safe_load_all(Path("src/crds.yaml").read_text())
                    ],
                }
            },
        )
        self.model.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(Operator)
