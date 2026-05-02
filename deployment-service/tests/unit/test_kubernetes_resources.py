import pytest

from deployment_service.kubernetes_resources import (
    build_custom_image_deployment,
    build_image_pull_secret,
    build_model_deployment,
    build_model_service,
    dns_label,
    model_service_port,
    parse_s3_uri,
    workload_names,
)


def test_parse_s3_uri_returns_bucket_and_key():
    assert parse_s3_uri("s3://models/user/repo/model.pkl") == ("models", "user/repo/model.pkl")


@pytest.mark.parametrize("uri", ["models/user/model.pkl", "s3://models", "s3:///key"])
def test_parse_s3_uri_rejects_invalid_values(uri):
    with pytest.raises(ValueError):
        parse_s3_uri(uri)


def test_dns_label_normalizes_and_truncates_names():
    assert dns_label("Fraud Prod!") == "fraud-prod"
    assert len(dns_label("x" * 100)) <= 52


def test_build_model_deployment_uses_init_container_for_minio_download():
    deployment_id = "00000000-0000-0000-0000-000000000001"
    manifest = build_model_deployment(
        deployment_id=deployment_id,
        deployment_slug="fraud-prod",
        model_s3_uri="s3://models/user/fraud/classifier/model.pkl",
        image="mldlc/sklearn-pickle-server:dev",
        minio_endpoint="minio:9000",
    )

    assert manifest["metadata"]["name"] == workload_names("fraud-prod", deployment_id).deployment_name
    assert manifest["metadata"]["name"].endswith("00000000")
    init = manifest["spec"]["template"]["spec"]["initContainers"][0]
    assert init["image"] == "minio/mc:latest"
    assert "mc cp" in init["args"][0]
    container = manifest["spec"]["template"]["spec"]["containers"][0]
    assert container["env"] == [{"name": "MODEL_PATH", "value": "/models/model.pkl"}]


def test_build_model_service_uses_cluster_ip():
    deployment_id = "00000000-0000-0000-0000-000000000001"
    manifest = build_model_service(
        deployment_id=deployment_id,
        deployment_slug="fraud-prod",
        service_type="ClusterIP",
    )

    assert manifest["spec"]["type"] == "ClusterIP"
    assert manifest["spec"]["ports"][0]["port"] == model_service_port(deployment_id)
    assert manifest["spec"]["ports"][0]["targetPort"] == "http"


def test_build_custom_image_deployment_skips_minio_init_container_and_uses_pull_secret():
    deployment_id = "00000000-0000-0000-0000-000000000001"
    manifest = build_custom_image_deployment(
        deployment_id=deployment_id,
        deployment_slug="fraud-prod",
        image="gitea.mldlc.local/mldlc-user/fraud:latest",
        image_pull_secret="pull-secret",
    )

    pod_spec = manifest["spec"]["template"]["spec"]
    assert "initContainers" not in pod_spec
    assert pod_spec["imagePullSecrets"] == [{"name": "pull-secret"}]
    assert pod_spec["containers"][0]["image"] == "gitea.mldlc.local/mldlc-user/fraud:latest"


def test_build_image_pull_secret_contains_docker_config_json():
    secret = build_image_pull_secret(
        deployment_id="00000000-0000-0000-0000-000000000001",
        registry_host="gitea.mldlc.local",
        username="mldlc-user",
        token="secret-token",
    )

    assert secret["type"] == "kubernetes.io/dockerconfigjson"
    assert "gitea.mldlc.local" in secret["stringData"][".dockerconfigjson"]
