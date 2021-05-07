"""Kubernetes Traefik Middleware Reconciler"""
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from dacite import from_dict
from kubernetes.client import ApiextensionsV1Api, CustomObjectsApi

from authentik.outposts.controllers.base import FIELD_MANAGER
from authentik.outposts.controllers.k8s.base import (
    Disabled,
    KubernetesObjectReconciler,
    NeedsUpdate,
)
from authentik.providers.proxy.models import ProxyProvider

if TYPE_CHECKING:
    from authentik.outposts.controllers.kubernetes import KubernetesController


@dataclass
class TraefikMiddlewareSpecForwardAuth:
    """traefik middleware forwardAuth spec"""

    address: str
    # pylint: disable=invalid-name
    authResponseHeaders: list[str]
    # pylint: disable=invalid-name
    trustForwardHeader: bool


@dataclass
class TraefikMiddlewareSpec:
    """Traefik middleware spec"""

    # pylint: disable=invalid-name
    forwardAuth: TraefikMiddlewareSpecForwardAuth


@dataclass
class TraefikMiddlewareMetadata:
    """Traefik Middleware metadata"""

    name: str
    namespace: str
    labels: dict = field(default_factory=dict)


@dataclass
class TraefikMiddleware:
    """Traefik Middleware"""

    # pylint: disable=invalid-name
    apiVersion: str
    kind: str
    metadata: TraefikMiddlewareMetadata
    spec: TraefikMiddlewareSpec


CRD_NAME = "middlewares.traefik.containo.us"
CRD_GROUP = "traefik.containo.us"
CRD_VERSION = "v1alpha1"
CRD_PLURAL = "middlewares"


class TraefikMiddlewareReconciler(KubernetesObjectReconciler[TraefikMiddleware]):
    """Kubernetes Traefik Middleware Reconciler"""

    def __init__(self, controller: "KubernetesController") -> None:
        super().__init__(controller)
        self.api_ex = ApiextensionsV1Api(controller.client)
        self.api = CustomObjectsApi(controller.client)

    def _crd_exists(self) -> bool:
        """Check if the traefik middleware exists"""
        return bool(
            len(
                self.api_ex.list_custom_resource_definition(
                    field_selector=f"metadata.name={CRD_NAME}"
                ).items
            )
        )

    def reconcile(self, current: TraefikMiddleware, reference: TraefikMiddleware):
        super().reconcile(current, reference)
        if current.spec.forwardAuth.address != reference.spec.forwardAuth.address:
            raise NeedsUpdate()

    def get_reference_object(self) -> TraefikMiddleware:
        """Get deployment object for outpost"""
        if not ProxyProvider.objects.filter(
            outpost__in=[self.controller.outpost],
            forward_auth_mode=True,
        ).exists():
            raise Disabled()
        if not self._crd_exists():
            raise Disabled()
        return TraefikMiddleware(
            apiVersion=f"{CRD_GROUP}/{CRD_VERSION}",
            kind="Middleware",
            metadata=TraefikMiddlewareMetadata(
                name=self.name,
                namespace=self.namespace,
                labels=self.get_object_meta().labels,
            ),
            spec=TraefikMiddlewareSpec(
                forwardAuth=TraefikMiddlewareSpecForwardAuth(
                    address=f"http://{self.name}.{self.namespace}:4180/akprox/auth?traefik",
                    authResponseHeaders=[
                        "Set-Cookie",
                        "X-Auth-Username",
                        "X-Forwarded-Email",
                        "X-Forwarded-Preferred-Username",
                        "X-Forwarded-User",
                    ],
                    trustForwardHeader=True,
                )
            ),
        )

    def create(self, reference: TraefikMiddleware):
        return self.api.create_namespaced_custom_object(
            group=CRD_GROUP,
            version=CRD_VERSION,
            plural=CRD_PLURAL,
            namespace=self.namespace,
            body=asdict(reference),
            field_manager=FIELD_MANAGER,
        )

    def delete(self, reference: TraefikMiddleware):
        return self.api.delete_namespaced_custom_object(
            group=CRD_GROUP,
            version=CRD_VERSION,
            namespace=self.namespace,
            plural=CRD_PLURAL,
            name=self.name,
        )

    def retrieve(self) -> TraefikMiddleware:
        return from_dict(
            TraefikMiddleware,
            self.api.get_namespaced_custom_object(
                group=CRD_GROUP,
                version=CRD_VERSION,
                namespace=self.namespace,
                plural=CRD_PLURAL,
                name=self.name,
            ),
        )

    def update(self, current: TraefikMiddleware, reference: TraefikMiddleware):
        return self.api.patch_namespaced_custom_object(
            group=CRD_GROUP,
            version=CRD_VERSION,
            namespace=self.namespace,
            plural=CRD_PLURAL,
            name=self.name,
            body=asdict(reference),
            field_manager=FIELD_MANAGER,
        )
