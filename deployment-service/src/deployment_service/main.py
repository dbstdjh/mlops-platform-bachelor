from __future__ import annotations

import asyncio
import logging

from deployment_service.config import Settings
from deployment_service.db import DeploymentDatabase
from deployment_service.kubernetes_client import KubernetesDeployer
from deployment_service.worker import DeploymentWorker


async def async_main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    database = await DeploymentDatabase.connect(settings.asyncpg_database_url)
    try:
        await database.ensure_deployment_statuses()
        worker = DeploymentWorker(
            database=database,
            deployer=KubernetesDeployer.in_cluster(settings),
            settings=settings,
        )
        await worker.run_forever()
    finally:
        await database.close()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
