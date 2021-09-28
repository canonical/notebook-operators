# Copyright 2021 Canonical
# See LICENSE file for licensing details.
import logging

from kubernetes import kubernetes

logger = logging.getLogger(__name__)


class JupyterUIResources:
    """Class to handle the creation and deletion of those Kubernetes resources
    required by the JupyterUI, but not automatically handled by Juju"""

    def __init__(self, charm):
        self.model = charm.model
        self.app = charm.app
        self.config = charm.config
        # Setup some Kubernetes API clients we'll need
        kcl = kubernetes.client.ApiClient()
        self.apps_api = kubernetes.client.AppsV1Api(kcl)
        self.core_api = kubernetes.client.CoreV1Api(kcl)
        self.auth_api = kubernetes.client.RbacAuthorizationV1Api(kcl)

    def apply(self) -> None:
        """Create the required Kubernetes resources for the dashboard"""
        # Create Kubernetes Cluster Roles
        for cr in self._clusterroles:
            r = self.auth_api.list_cluster_role(
                field_selector=f"metadata.name={cr['body'].metadata.name}",
            )
            if not r.items:
                self.auth_api.create_cluster_role(**cr)
            else:
                logger.info("cluster role '%s' exists, patching", cr["body"].metadata.name)
                self.auth_api.patch_cluster_role(name=cr["body"].metadata.name, **cr)
        # Create Kubernetes Services
        for service in self._services:
            s = self.core_api.list_namespaced_service(
                namespace=service["namespace"],
                field_selector=f"metadata.name={service['body'].metadata.name}",
            )
            if not s.items:
                self.core_api.create_namespaced_service(**service)
            else:
                logger.info(
                    "service '%s' in namespace '%s' exists, patching",
                    service["body"].metadata.name,
                    service["namespace"],
                )
                self.core_api.patch_namespaced_service(
                    name=service["body"].metadata.name, **service
                )

    def delete(self) -> None:
        """Delete all of the Kubernetes resources created by the apply method"""
        # Delete Kubernetes cluster roles
        for cr in self._clusterroles:
            self.auth_api.delete_cluster_role(name=cr["body"].metadata.name)
        # Delete Kubernetes services
        for service in self._services:
            self.core_api.delete_namespaced_service(
                namespace=service["namespace"], name=service["body"].metadata.name
            )

    @property
    def _clusterroles(self) -> list:
        """Return a list of Cluster Roles required by the Jupyter UI"""
        return [
            {
                "body": kubernetes.client.V1ClusterRole(
                    api_version="rbac.authorization.k8s.io/v1",
                    metadata=kubernetes.client.V1ObjectMeta(
                        name="jupyter-jupyter-ui",
                        labels={"app.kubernetes.io/name": self.app.name},
                    ),
                    rules=[
                        # Allow Metrics Scraper to get metrics from the Metrics server
                        kubernetes.client.V1PolicyRule(
                            api_groups=[""],
                            resources=["namespaces"],
                            verbs=["get", "list", "create", "delete"],
                        ),
                        kubernetes.client.V1PolicyRule(
                            api_groups=["authorization.k8s.io"],
                            resources=["subjectaccessreviews"],
                            verbs=["create"],
                        ),
                        kubernetes.client.V1PolicyRule(
                            api_groups=["kubeflow.org"],
                            resources=["notebooks", "notebooks/finalizers", "poddefaults"],
                            verbs=['get', 'list', 'create', 'delete', 'patch', 'update'],
                        ),
                        kubernetes.client.V1PolicyRule(
                            api_groups=[""],
                            resources=["persistentvolumeclaims"],
                            verbs=['create', 'delete', 'get', 'list'],
                        ),
                        kubernetes.client.V1PolicyRule(
                            api_groups=[""],
                            resources=['events', 'nodes'],
                            verbs=['list'],
                        ),
                        kubernetes.client.V1PolicyRule(
                            api_groups=['storage.k8s.io'],
                            resources=['storageclasses'],
                            verbs=['get', 'list', 'watch'],
                        ),
                    ],
                )
            }
        ]

    @property
    def _services(self) -> list:
        """Return a list of Kubernetes services needed by the Jupyter UI"""
        # Note that this service is actually created by Juju, we are patching
        # it here to include the correct port mapping
        # TODO: Update when support improves in Juju

        return [
            {
                "namespace": self.model.name,
                "body": kubernetes.client.V1Service(
                    api_version="v1",
                    metadata=kubernetes.client.V1ObjectMeta(
                        namespace=self.model.name,
                        name=self.app.name,
                        labels={"app.kubernetes.io/name": self.app.name},
                    ),
                    spec=kubernetes.client.V1ServiceSpec(
                        ports=[
                            kubernetes.client.V1ServicePort(
                                name="http",
                                port=self.config['port'],
                                target_port=self.config['port'],
                            )
                        ],
                        selector={"app.kubernetes.io/name": self.app.name},
                    ),
                ),
            }
        ]
