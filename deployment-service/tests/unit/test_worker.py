from dataclasses import dataclass

import pytest

from deployment_service.config import Settings
from deployment_service.db import DeploymentSpec, DeploymentTask
from deployment_service.kubernetes_client import ProvisionedEndpoint
from deployment_service.worker import DeploymentWorker


@dataclass
class FakeDatabase:
    tasks: list[DeploymentTask]
    statuses: list[str]
    task_statuses: list[str]

    def __init__(self, tasks):
        self.tasks = list(tasks)
        self.statuses = []
        self.task_statuses = []
        self.spec = DeploymentSpec(
            deployment_id="00000000-0000-0000-0000-000000000001",
            user_id="00000000-0000-0000-0000-000000000002",
            deployment_slug="fraud-prod",
            source_type="file",
            model_s3_uri="s3://models/user/fraud/model.pkl",
            model_file_type="pickle",
        )
        self.active_endpoint = None

    async def claim_next_task(self):
        return self.tasks.pop(0) if self.tasks else None

    async def fetch_deployment_spec(self, deployment_id):
        return self.spec

    async def mark_deployment_status(self, deployment_id, status):
        self.statuses.append(status)

    async def mark_deployment_active(self, deployment_id, **kwargs):
        self.statuses.append("ACTIVE")
        self.active_endpoint = kwargs

    async def mark_task_completed(self, task_id):
        self.task_statuses.append("COMPLETED")

    async def mark_task_failed(self, task_id, error_message):
        self.task_statuses.append(f"FAILED:{error_message}")


class FakeDeployer:
    def __init__(self, fail=False):
        self.fail = fail
        self.deleted = False

    async def deploy(self, spec):
        if self.fail:
            raise RuntimeError("broken rollout")
        self.deployed_spec = spec
        return ProvisionedEndpoint(
            endpoint_url="http://gateway.mldlc.local/api/v1/deployments/fraud-prod:predict",
            namespace="mldlc",
            deployment_name="model-fraud-prod",
            service_name="model-fraud-prod",
            service_port=20001,
        )

    async def delete(self, spec):
        self.deleted = True


@pytest.mark.asyncio
async def test_process_deploy_task_marks_active_and_completed():
    db = FakeDatabase([DeploymentTask(id="task-1", deployment_id="dep-1", type="DEPLOY")])
    worker = DeploymentWorker(database=db, deployer=FakeDeployer(), settings=Settings())

    await worker.process_pending_tasks()

    assert db.statuses == ["DEPLOYING", "ACTIVE"]
    assert db.task_statuses == ["COMPLETED"]
    assert db.active_endpoint["endpoint_url"] == "http://gateway.mldlc.local/api/v1/deployments/fraud-prod:predict"
    assert db.active_endpoint["k8s_service_port"] == 20001


@pytest.mark.asyncio
async def test_process_delete_task_marks_deleted_and_completed():
    db = FakeDatabase([DeploymentTask(id="task-1", deployment_id="dep-1", type="DELETE")])
    deployer = FakeDeployer()
    worker = DeploymentWorker(database=db, deployer=deployer, settings=Settings())

    await worker.process_pending_tasks()

    assert deployer.deleted is True
    assert db.statuses == ["DELETING", "DELETED"]
    assert db.task_statuses == ["COMPLETED"]


@pytest.mark.asyncio
async def test_process_task_records_failure():
    db = FakeDatabase([DeploymentTask(id="task-1", deployment_id="dep-1", type="DEPLOY")])
    worker = DeploymentWorker(database=db, deployer=FakeDeployer(fail=True), settings=Settings())

    await worker.process_pending_tasks()

    assert db.statuses == ["DEPLOYING", "FAILED"]
    assert db.task_statuses == ["FAILED:broken rollout"]
