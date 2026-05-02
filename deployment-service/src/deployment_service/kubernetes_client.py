from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
from kubernetes import client, config
from kubernetes.client import ApiException

from deployment_service.config import Settings
from deployment_service.db import DeploymentSpec
from deployment_service.kubernetes_resources import (
    build_custom_image_deployment,
    build_image_pull_secret,
    build_model_deployment,
    build_model_service,
    image_pull_secret_name,
    model_service_port,
    workload_names,
)
from deployment_service.secrets import SecretCipher


@dataclass(frozen=True)
class ProvisionedEndpoint:
    endpoint_url: str
    namespace: str
    deployment_name: str
    service_name: str
    service_port: int


class KubernetesDeployer:
    def __init__(
        self,
        *,
        apps_api: client.AppsV1Api,
        core_api: client.CoreV1Api,
        settings: Settings,
    ):
        self._apps_api = apps_api
        self._core_api = core_api
        self._settings = settings
        self._cipher = SecretCipher(settings.secret_key)

    @classmethod
    def in_cluster(cls, settings: Settings) -> "KubernetesDeployer":
        config.load_incluster_config()
        return cls(
            apps_api=client.AppsV1Api(),
            core_api=client.CoreV1Api(),
            settings=settings,
        )

    async def deploy(self, spec: DeploymentSpec) -> ProvisionedEndpoint:
        if spec.source_type == "file" and spec.model_file_type != "pickle":
            raise ValueError("Only pickle model deployments are supported in V1")

        names = workload_names(spec.deployment_slug, spec.deployment_id)
        namespace = self._settings.namespace
        if spec.source_type == "image":
            if not spec.image_ref:
                raise ValueError("Image deployment is missing an image reference")
            pull_secret_name = None
            if spec.encrypted_registry_token and spec.registry_host and spec.registry_username:
                token = self._cipher.decrypt(spec.encrypted_registry_token)
                secret = build_image_pull_secret(
                    deployment_id=spec.deployment_id,
                    registry_host=spec.registry_host,
                    username=spec.registry_username,
                    token=token,
                )
                pull_secret_name = image_pull_secret_name(spec.deployment_id)
                await asyncio.to_thread(self._apply_secret, namespace, pull_secret_name, secret)
            deployment = build_custom_image_deployment(
                deployment_id=spec.deployment_id,
                deployment_slug=spec.deployment_slug,
                image=spec.image_ref,
                image_pull_secret=pull_secret_name,
            )
        else:
            deployment = build_model_deployment(
                deployment_id=spec.deployment_id,
                deployment_slug=spec.deployment_slug,
                model_s3_uri=spec.model_s3_uri or "",
                image=self._settings.prebuilt_pickle_image,
                minio_endpoint=self._settings.minio_endpoint,
            )
        service = build_model_service(
            deployment_id=spec.deployment_id,
            deployment_slug=spec.deployment_slug,
            service_type=self._settings.model_service_type,
        )

        await asyncio.to_thread(self._apply_deployment, namespace, names.deployment_name, deployment)
        await asyncio.to_thread(self._apply_service, namespace, names.service_name, service)
        await self._wait_for_available_deployment(namespace, names.deployment_name)
        service_port = model_service_port(spec.deployment_id)
        await self._wait_for_ready(
            self._cluster_ready_url(
                namespace,
                names.service_name,
                service_port,
            )
        )
        return ProvisionedEndpoint(
            endpoint_url=self._gateway_predict_url(spec.deployment_slug),
            namespace=namespace,
            deployment_name=names.deployment_name,
            service_name=names.service_name,
            service_port=service_port,
        )

    async def delete(self, spec: DeploymentSpec) -> None:
        names = workload_names(spec.deployment_slug, spec.deployment_id)
        namespace = self._settings.namespace
        await asyncio.to_thread(self._delete_deployment, namespace, names.deployment_name)
        await asyncio.to_thread(self._delete_service, namespace, names.service_name)
        if spec.source_type == "image":
            await asyncio.to_thread(self._delete_secret, namespace, image_pull_secret_name(spec.deployment_id))

    def _apply_deployment(self, namespace: str, name: str, body: dict[str, Any]) -> None:
        try:
            self._apps_api.read_namespaced_deployment(name=name, namespace=namespace)
        except ApiException as exc:
            if exc.status != 404:
                raise
            self._apps_api.create_namespaced_deployment(namespace=namespace, body=body)
            return
        self._apps_api.patch_namespaced_deployment(name=name, namespace=namespace, body=body)

    def _apply_service(self, namespace: str, name: str, body: dict[str, Any]) -> None:
        try:
            self._core_api.read_namespaced_service(name=name, namespace=namespace)
        except ApiException as exc:
            if exc.status != 404:
                raise
            self._core_api.create_namespaced_service(namespace=namespace, body=body)
            return
        self._core_api.patch_namespaced_service(name=name, namespace=namespace, body=body)

    def _apply_secret(self, namespace: str, name: str, body: dict[str, Any]) -> None:
        try:
            self._core_api.read_namespaced_secret(name=name, namespace=namespace)
        except ApiException as exc:
            if exc.status != 404:
                raise
            self._core_api.create_namespaced_secret(namespace=namespace, body=body)
            return
        self._core_api.patch_namespaced_secret(name=name, namespace=namespace, body=body)

    def _delete_deployment(self, namespace: str, name: str) -> None:
        try:
            self._apps_api.delete_namespaced_deployment(name=name, namespace=namespace)
        except ApiException as exc:
            if exc.status != 404:
                raise

    def _delete_service(self, namespace: str, name: str) -> None:
        try:
            self._core_api.delete_namespaced_service(name=name, namespace=namespace)
        except ApiException as exc:
            if exc.status != 404:
                raise

    def _delete_secret(self, namespace: str, name: str) -> None:
        try:
            self._core_api.delete_namespaced_secret(name=name, namespace=namespace)
        except ApiException as exc:
            if exc.status != 404:
                raise

    async def _wait_for_available_deployment(self, namespace: str, name: str) -> None:
        deadline = asyncio.get_running_loop().time() + self._settings.rollout_timeout_seconds
        while True:
            deployment = await asyncio.to_thread(
                self._apps_api.read_namespaced_deployment,
                name=name,
                namespace=namespace,
            )
            status = deployment.status
            available = status.available_replicas or 0
            desired = deployment.spec.replicas or 1
            if available >= desired:
                return
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"Deployment '{name}' did not become available")
            await asyncio.sleep(self._settings.poll_interval_seconds)

    async def _wait_for_endpoint(self, namespace: str, name: str) -> str:
        deadline = asyncio.get_running_loop().time() + self._settings.endpoint_timeout_seconds
        while True:
            service = await asyncio.to_thread(
                self._core_api.read_namespaced_service,
                name=name,
                namespace=namespace,
            )
            endpoint = self._endpoint_from_service(service)
            if endpoint:
                return endpoint
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"Service '{name}' did not receive a LoadBalancer endpoint")
            await asyncio.sleep(self._settings.poll_interval_seconds)

    async def _wait_for_ready(self, endpoint_url: str) -> None:
        deadline = asyncio.get_running_loop().time() + self._settings.ready_timeout_seconds
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as http:
            while True:
                try:
                    response = await http.get(endpoint_url)
                    if response.status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError(f"Model endpoint '{endpoint_url}' did not become ready")
                await asyncio.sleep(self._settings.poll_interval_seconds)

    def _endpoint_from_service(self, service) -> str | None:
        ingress_items = service.status.load_balancer.ingress if service.status.load_balancer else None
        if not ingress_items:
            return None
        ingress = ingress_items[0]
        host = ingress.hostname or ingress.ip
        if not host:
            return None
        port = service.spec.ports[0].port
        return f"http://{host}:{port}/predict"

    def _cluster_ready_url(self, namespace: str, service_name: str, service_port: int) -> str:
        return f"http://{service_name}.{namespace}.svc.cluster.local:{service_port}/ready"

    def _gateway_predict_url(self, deployment_slug: str) -> str:
        return f"{self._settings.gateway_public_url.rstrip('/')}/api/v1/deployments/{deployment_slug}:predict"
