from deployment_service.config import Settings
from deployment_service.kubernetes_client import KubernetesDeployer


def test_cluster_ready_url_uses_service_dns_instead_of_external_load_balancer_url():
    deployer = KubernetesDeployer(apps_api=object(), core_api=object(), settings=Settings())

    assert (
        deployer._cluster_ready_url("mldlc", "model-fraud-prod", 23456)
        == "http://model-fraud-prod.mldlc.svc.cluster.local:23456/ready"
    )


def test_gateway_predict_url_uses_public_gateway_url_and_deployment_slug():
    deployer = KubernetesDeployer(
        apps_api=object(),
        core_api=object(),
        settings=Settings(gateway_public_url="http://gateway.mldlc.local/"),
    )

    assert (
        deployer._gateway_predict_url("fraud-prod")
        == "http://gateway.mldlc.local/api/v1/deployments/fraud-prod:predict"
    )
