"""
Ports for external observability integrations.
"""

import uuid
from abc import ABC, abstractmethod

from src.core.entities.dashboard import DeploymentPlotSource, DeploymentPlotType, PlotType


class GrafanaDashboardClient(ABC):
    """Port for provisioning and embedding Grafana dashboards."""

    @abstractmethod
    async def upsert_run_plot(
        self,
        *,
        grafana_uid: str | None,
        title: str,
        run_id: uuid.UUID,
        plot_type: PlotType,
        metrics: list[str],
    ) -> str:
        ...

    @abstractmethod
    async def upsert_deployment_plot(
        self,
        *,
        grafana_uid: str | None,
        title: str,
        deployment_id: uuid.UUID,
        plot_type: DeploymentPlotType | str,
        source: DeploymentPlotSource | str,
        field_path: str | None = None,
        field_type: str | None = None,
    ) -> str:
        ...

    @abstractmethod
    async def delete_dashboard(self, grafana_uid: str) -> None:
        ...

    @abstractmethod
    def build_solo_iframe_url(self, grafana_uid: str) -> str:
        ...
