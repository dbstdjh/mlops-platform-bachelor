from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelWorkloadNames:
    deployment_name: str
    service_name: str


def parse_s3_uri(s3_uri: str) -> tuple[str, str]:
    if not s3_uri.startswith("s3://"):
        raise ValueError("Model artifact URI must start with s3://")
    bucket_and_key = s3_uri.removeprefix("s3://")
    bucket, separator, key = bucket_and_key.partition("/")
    if not bucket or not separator or not key:
        raise ValueError("Model artifact URI must include bucket and object key")
    return bucket, key


def workload_names(deployment_slug: str, deployment_id: str) -> ModelWorkloadNames:
    suffix = deployment_id.replace("-", "")[:8]
    base = dns_label(f"model-{deployment_slug}-{suffix}")
    return ModelWorkloadNames(deployment_name=base, service_name=base)


def model_service_port(deployment_id: str) -> int:
    hex_digits = deployment_id.replace("-", "")[:8]
    return 20000 + (int(hex_digits, 16) % 10000)


def dns_label(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    normalized = re.sub(r"-+", "-", normalized)
    if not normalized:
        normalized = "deployment"
    if len(normalized) > 52:
        normalized = normalized[:52].rstrip("-")
    return normalized


def managed_labels(deployment_id: str, deployment_slug: str) -> dict[str, str]:
    return {
        "app.kubernetes.io/name": workload_names(deployment_slug, deployment_id).deployment_name,
        "app.kubernetes.io/component": "model-server",
        "app.kubernetes.io/managed-by": "deployment-service",
        "mldlc/deployment-id": deployment_id,
    }


def image_pull_secret_name(deployment_id: str) -> str:
    suffix = deployment_id.replace("-", "")[:12]
    return dns_label(f"gitea-pull-{suffix}")


def build_image_pull_secret(
    *,
    deployment_id: str,
    registry_host: str,
    username: str,
    token: str,
) -> dict:
    auth = base64.b64encode(f"{username}:{token}".encode("utf-8")).decode("ascii")
    docker_config = {
        "auths": {
            registry_host: {
                "username": username,
                "password": token,
                "auth": auth,
            }
        }
    }
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": image_pull_secret_name(deployment_id)},
        "type": "kubernetes.io/dockerconfigjson",
        "stringData": {".dockerconfigjson": json.dumps(docker_config)},
    }


def build_model_deployment(
    *,
    deployment_id: str,
    deployment_slug: str,
    model_s3_uri: str,
    image: str,
    minio_endpoint: str,
) -> dict:
    bucket, key = parse_s3_uri(model_s3_uri)
    names = workload_names(deployment_slug, deployment_id)
    labels = managed_labels(deployment_id, deployment_slug)
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": names.deployment_name, "labels": labels},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "initContainers": [
                        {
                            "name": "fetch-model",
                            "image": "minio/mc:latest",
                            "env": [
                                {
                                    "name": "MINIO_ACCESS_KEY",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "platform-secret",
                                            "key": "MINIO_ACCESS_KEY",
                                        }
                                    },
                                },
                                {
                                    "name": "MINIO_SECRET_KEY",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "platform-secret",
                                            "key": "MINIO_SECRET_KEY",
                                        }
                                    },
                                },
                            ],
                            "command": ["/bin/sh", "-c"],
                            "args": [
                                (
                                    f'mc alias set models http://{minio_endpoint} "$MINIO_ACCESS_KEY" '
                                    f'"$MINIO_SECRET_KEY" && mc cp "models/{bucket}/{key}" /models/model.pkl'
                                )
                            ],
                            "volumeMounts": [{"name": "model-artifact", "mountPath": "/models"}],
                        }
                    ],
                    "containers": [
                        {
                            "name": "model",
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "ports": [{"name": "http", "containerPort": 8000}],
                            "env": [{"name": "MODEL_PATH", "value": "/models/model.pkl"}],
                            "readinessProbe": {
                                "httpGet": {"path": "/ready", "port": "http"},
                                "initialDelaySeconds": 5,
                                "periodSeconds": 5,
                            },
                            "livenessProbe": {
                                "httpGet": {"path": "/health", "port": "http"},
                                "initialDelaySeconds": 10,
                                "periodSeconds": 10,
                            },
                            "volumeMounts": [{"name": "model-artifact", "mountPath": "/models"}],
                        }
                    ],
                    "volumes": [{"name": "model-artifact", "emptyDir": {}}],
                },
            },
        },
    }


def build_custom_image_deployment(
    *,
    deployment_id: str,
    deployment_slug: str,
    image: str,
    image_pull_secret: str | None = None,
) -> dict:
    names = workload_names(deployment_slug, deployment_id)
    labels = managed_labels(deployment_id, deployment_slug)
    pod_spec = {
        "containers": [
            {
                "name": "model",
                "image": image,
                "imagePullPolicy": "IfNotPresent",
                "ports": [{"name": "http", "containerPort": 8000}],
                "readinessProbe": {
                    "httpGet": {"path": "/ready", "port": "http"},
                    "initialDelaySeconds": 5,
                    "periodSeconds": 5,
                },
                "livenessProbe": {
                    "httpGet": {"path": "/health", "port": "http"},
                    "initialDelaySeconds": 10,
                    "periodSeconds": 10,
                },
            }
        ]
    }
    if image_pull_secret:
        pod_spec["imagePullSecrets"] = [{"name": image_pull_secret}]
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": names.deployment_name, "labels": labels},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {"labels": labels},
                "spec": pod_spec,
            },
        },
    }


def build_model_service(
    *,
    deployment_id: str,
    deployment_slug: str,
    service_type: str,
) -> dict:
    names = workload_names(deployment_slug, deployment_id)
    labels = managed_labels(deployment_id, deployment_slug)
    port = model_service_port(deployment_id)
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": names.service_name, "labels": labels},
        "spec": {
            "type": service_type,
            "selector": labels,
            "ports": [{"name": "http", "port": port, "targetPort": "http"}],
        },
    }
