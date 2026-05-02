from __future__ import annotations

import logging

from deployment_service.config import Settings
from deployment_service.db import DeploymentDatabase, DeploymentTask
from deployment_service.kubernetes_client import KubernetesDeployer

logger = logging.getLogger(__name__)


class DeploymentWorker:
    def __init__(
        self,
        *,
        database: DeploymentDatabase,
        deployer: KubernetesDeployer,
        settings: Settings,
    ):
        self._database = database
        self._deployer = deployer
        self._settings = settings

    async def run_forever(self) -> None:
        await self.process_pending_tasks()
        async for _notification in self._database.listen(self._settings.listen_channel):
            await self.process_pending_tasks()

    async def process_pending_tasks(self) -> None:
        while True:
            task = await self._database.claim_next_task()
            if task is None:
                return
            await self.process_task(task)

    async def process_task(self, task: DeploymentTask) -> None:
        try:
            spec = await self._database.fetch_deployment_spec(task.deployment_id)
            if task.type == "DEPLOY":
                await self._database.mark_deployment_status(task.deployment_id, "DEPLOYING")
                endpoint = await self._deployer.deploy(spec)
                await self._database.mark_deployment_active(
                    task.deployment_id,
                    endpoint_url=endpoint.endpoint_url,
                    namespace=endpoint.namespace,
                    k8s_deployment_name=endpoint.deployment_name,
                    k8s_service_name=endpoint.service_name,
                    k8s_service_port=endpoint.service_port,
                )
            elif task.type == "DELETE":
                await self._database.mark_deployment_status(task.deployment_id, "DELETING")
                await self._deployer.delete(spec)
                await self._database.mark_deployment_status(task.deployment_id, "DELETED")
            else:
                raise ValueError(f"Unsupported deployment task type '{task.type}'")
            await self._database.mark_task_completed(task.id)
        except Exception as exc:
            logger.exception("Deployment task %s failed", task.id)
            await self._database.mark_deployment_status(task.deployment_id, "FAILED")
            await self._database.mark_task_failed(task.id, str(exc))
