"""
Infrastructure adapter for Grafana dashboard provisioning.
"""

import uuid
from typing import Any

import httpx
from sqlalchemy.engine import make_url

from src.core.entities.dashboard import PlotType
from src.core.ports.observability import GrafanaDashboardClient


class GrafanaProvisioningError(Exception):
    """Raised when Grafana provisioning fails."""


class HttpGrafanaDashboardClient(GrafanaDashboardClient):
    """Provision run-plot dashboards through Grafana's HTTP API."""

    def __init__(
        self,
        *,
        grafana_url: str,
        public_url: str,
        admin_token: str,
        admin_user: str,
        admin_password: str,
        datasource_name: str,
        datasource_host: str,
        datasource_port: int,
        datasource_database: str,
        datasource_user: str,
        datasource_password: str,
        datasource_sslmode: str,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._grafana_url = grafana_url.rstrip("/")
        self._public_url = public_url.rstrip("/")
        self._admin_token = admin_token
        self._admin_user = admin_user
        self._admin_password = admin_password
        self._datasource_name = datasource_name
        self._datasource_host = datasource_host
        self._datasource_port = datasource_port
        self._datasource_database = datasource_database
        self._datasource_user = datasource_user
        self._datasource_password = datasource_password
        self._datasource_sslmode = datasource_sslmode
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    @classmethod
    def from_settings(
        cls,
        *,
        grafana_url: str,
        public_url: str,
        admin_token: str,
        admin_user: str,
        admin_password: str,
        database_url: str,
        datasource_name: str,
        datasource_host: str | None = None,
        datasource_port: int | None = None,
        datasource_database: str | None = None,
        datasource_user: str | None = None,
        datasource_password: str | None = None,
        datasource_sslmode: str = "disable",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "HttpGrafanaDashboardClient":
        parsed_url = make_url(database_url)
        resolved_host = datasource_host or parsed_url.host or "db"
        resolved_port = datasource_port or int(parsed_url.port or 5432)
        resolved_database = datasource_database or parsed_url.database or "mlops"
        resolved_user = datasource_user or parsed_url.username or "mlops"
        resolved_password = datasource_password or parsed_url.password or "mlops"
        return cls(
            grafana_url=grafana_url,
            public_url=public_url,
            admin_token=admin_token,
            admin_user=admin_user,
            admin_password=admin_password,
            datasource_name=datasource_name,
            datasource_host=resolved_host,
            datasource_port=resolved_port,
            datasource_database=resolved_database,
            datasource_user=resolved_user,
            datasource_password=resolved_password,
            datasource_sslmode=datasource_sslmode,
            transport=transport,
        )

    async def upsert_run_plot(
        self,
        *,
        grafana_uid: str | None,
        title: str,
        run_id: uuid.UUID,
        plot_type: PlotType,
        metrics: list[str],
    ) -> str:
        datasource_uid = await self._ensure_postgres_datasource()
        uid = grafana_uid or uuid.uuid4().hex[:12]
        dashboard = {
            "uid": uid,
            "title": title,
            "timezone": "browser",
            "schemaVersion": 39,
            "version": 0,
            "editable": True,
            "panels": [
                self._build_panel(
                    datasource_uid=datasource_uid,
                    run_id=run_id,
                    plot_type=plot_type,
                    metrics=metrics,
                    title=title,
                )
            ],
            "time": {"from": "now-30d", "to": "now"},
            "refresh": "30s",
        }
        payload = {"dashboard": dashboard, "overwrite": True}

        async with self._client() as client:
            response = await client.post("/api/dashboards/db", json=payload)
        if response.status_code >= 400:
            raise GrafanaProvisioningError(f"Grafana dashboard upsert failed: {response.text}")
        return uid

    async def delete_dashboard(self, grafana_uid: str) -> None:
        async with self._client() as client:
            response = await client.delete(f"/api/dashboards/uid/{grafana_uid}")
        if response.status_code == 404:
            return
        if response.status_code >= 400:
            raise GrafanaProvisioningError(f"Grafana dashboard delete failed: {response.text}")

    def build_solo_iframe_url(self, grafana_uid: str) -> str:
        return f"{self._public_url}/d-solo/{grafana_uid}/run-plot?orgId=1&panelId=1&kiosk&theme=light"

    def _build_panel(
        self,
        *,
        datasource_uid: str,
        run_id: uuid.UUID,
        plot_type: PlotType,
        metrics: list[str],
        title: str,
    ) -> dict[str, Any]:
        if plot_type == "stat":
            return {
                "id": 1,
                "type": "stat",
                "title": title,
                "datasource": {"type": "postgres", "uid": datasource_uid},
                "gridPos": {"h": 12, "w": 24, "x": 0, "y": 0},
                "targets": self._build_targets(run_id=run_id, plot_type=plot_type, metrics=metrics),
                "options": self._build_panel_options(plot_type, metrics),
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "palette-classic"},
                    },
                    "overrides": [],
                },
            }

        return {
            "id": 1,
            "type": "trend",
            "title": title,
            "datasource": {"type": "postgres", "uid": datasource_uid},
            "gridPos": {"h": 12, "w": 24, "x": 0, "y": 0},
            "targets": self._build_targets(run_id=run_id, plot_type=plot_type, metrics=metrics),
            "options": self._build_panel_options(plot_type, metrics),
            "fieldConfig": {
                "defaults": {
                    "color": {"mode": "palette-classic"},
                    "custom": {
                        "axisPlacement": "auto",
                        "drawStyle": "line",
                        "lineInterpolation": "linear",
                        "lineWidth": 2,
                        "pointSize": 4,
                        "showPoints": "never",
                        "spanNulls": True,
                        "insertNulls": False,
                        "scaleDistribution": {"type": "linear"},
                    },
                },
                "overrides": [],
            },
        }

    def _build_targets(self, *, run_id: uuid.UUID, plot_type: PlotType, metrics: list[str]) -> list[dict[str, Any]]:
        if plot_type == "line":
            return [
                {
                    "refId": "A",
                    "format": "table",
                    "rawSql": self._build_line_plot_sql(run_id=run_id, metrics=metrics),
                    "editorMode": "code",
                }
            ]

        targets: list[dict[str, Any]] = []
        for index, metric in enumerate(metrics):
            ref_id = chr(ord("A") + index)
            raw_sql = self._build_metric_sql(run_id=run_id, plot_type=plot_type, metric=metric)
            targets.append(
                {
                    "refId": ref_id,
                    "format": "table",
                    "rawSql": raw_sql,
                    "editorMode": "code",
                }
            )
        return targets

    def _build_metric_sql(self, *, run_id: uuid.UUID, plot_type: PlotType, metric: str) -> str:
        quoted_metric = self._sql_string_literal(metric)
        quoted_run_id = self._sql_string_literal(str(run_id))
        if plot_type == "stat":
            return (
                "SELECT "
                f"CAST(logged_data->>{quoted_metric} AS double precision) AS value "
                "FROM run_step "
                f"WHERE run_id = {quoted_run_id} AND logged_data ? {quoted_metric} "
                "ORDER BY step DESC LIMIT 1"
            )

        raise ValueError(f"Unsupported plot type for single-metric query: {plot_type}")

    def _build_line_plot_sql(self, *, run_id: uuid.UUID, metrics: list[str]) -> str:
        if not metrics:
            raise ValueError("line plots must declare at least one metric")

        quoted_run_id = self._sql_string_literal(str(run_id))
        select_fields = ["step"]
        metric_filters: list[str] = []

        for metric in metrics:
            quoted_metric = self._sql_string_literal(metric)
            aliased_metric = self._sql_identifier(metric)
            select_fields.append(
                f"CAST(logged_data->>{quoted_metric} AS double precision) AS {aliased_metric}"
            )
            metric_filters.append(f"logged_data ? {quoted_metric}")

        return (
            f"SELECT {', '.join(select_fields)} "
            "FROM run_step "
            f"WHERE run_id = {quoted_run_id} AND ({' OR '.join(metric_filters)}) "
            "ORDER BY step ASC"
        )

    def _build_panel_options(self, plot_type: PlotType, metrics: list[str]) -> dict[str, Any]:
        if plot_type == "stat":
            return {
                "colorMode": "value",
                "graphMode": "none",
                "justifyMode": "center",
                "orientation": "horizontal",
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                "textMode": "auto",
            }

        return {
            "xField": "step",
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": len(metrics) > 1},
            "tooltip": {"mode": "multi", "sort": "none"},
        }

    def _sql_identifier(self, value: str) -> str:
        escaped = value.replace('"', '""')
        return f'"{escaped}"'

    def _sql_string_literal(self, value: str) -> str:
        escaped = value.replace("'", "''")
        return f"'{escaped}'"

    async def _ensure_postgres_datasource(self) -> str:
        async with self._client() as client:
            lookup = await client.get(f"/api/datasources/name/{self._datasource_name}")
            if lookup.status_code == 200:
                payload = lookup.json()
                uid = payload.get("uid")
                if uid:
                    return str(uid)
            if lookup.status_code not in {200, 404}:
                raise GrafanaProvisioningError(f"Grafana datasource lookup failed: {lookup.text}")

            create_payload = {
                "name": self._datasource_name,
                "type": "postgres",
                "access": "proxy",
                "url": f"{self._datasource_host}:{self._datasource_port}",
                "database": self._datasource_database,
                "user": self._datasource_user,
                "secureJsonData": {"password": self._datasource_password},
                "jsonData": {
                    "database": self._datasource_database,
                    "postgresVersion": 1500,
                    "sslmode": self._datasource_sslmode,
                    "timescaledb": False,
                },
            }
            created = await client.post("/api/datasources", json=create_payload)
            if created.status_code not in {200, 201, 409}:
                raise GrafanaProvisioningError(f"Grafana datasource create failed: {created.text}")

            confirm = await client.get(f"/api/datasources/name/{self._datasource_name}")
            if confirm.status_code >= 400:
                raise GrafanaProvisioningError(f"Grafana datasource confirmation failed: {confirm.text}")
            payload = confirm.json()
            uid = payload.get("uid")
            if not uid:
                raise GrafanaProvisioningError("Grafana datasource confirmation did not return a UID")
            return str(uid)

    def _client(self) -> httpx.AsyncClient:
        headers = {"Accept": "application/json"}
        auth: tuple[str, str] | None = None
        if self._admin_token:
            headers["Authorization"] = f"Bearer {self._admin_token}"
        else:
            auth = (self._admin_user, self._admin_password)
        return httpx.AsyncClient(
            base_url=self._grafana_url,
            headers=headers,
            auth=auth,
            timeout=self._timeout_seconds,
            transport=self._transport,
            trust_env=False,
        )
