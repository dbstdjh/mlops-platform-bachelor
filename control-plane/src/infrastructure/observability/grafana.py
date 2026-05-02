"""
Infrastructure adapter for Grafana dashboard provisioning.
"""

import uuid
from typing import Any

import httpx
from sqlalchemy.engine import make_url

from src.core.entities.dashboard import DeploymentPlotSource, DeploymentPlotType, PlotType
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
                self._build_deployment_panel(
                    datasource_uid=datasource_uid,
                    deployment_id=deployment_id,
                    plot_type=plot_type,
                    source=source,
                    field_path=field_path,
                    field_type=field_type,
                    title=title,
                )
            ],
            "time": {"from": "now-24h", "to": "now"},
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

    def _build_deployment_panel(
        self,
        *,
        datasource_uid: str,
        deployment_id: uuid.UUID,
        plot_type: DeploymentPlotType | str,
        source: DeploymentPlotSource | str,
        field_path: str | None,
        field_type: str | None,
        title: str,
    ) -> dict[str, Any]:
        panel_type = "timeseries"
        options: dict[str, Any] = {
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": False},
            "tooltip": {"mode": "single", "sort": "none"},
        }
        field_config: dict[str, Any] = {
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
        }

        if plot_type in {"status_code", "distribution"}:
            panel_type = "barchart"
            options = {
                "legend": {"displayMode": "list", "placement": "bottom", "showLegend": False},
                "tooltip": {"mode": "single", "sort": "none"},
                "xField": "bucket",
            }
            field_config = {"defaults": {"color": {"mode": "palette-classic"}}, "overrides": []}
        elif plot_type == "category_time_series":
            options = {
                "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                "tooltip": {"mode": "multi", "sort": "desc"},
            }

        return {
            "id": 1,
            "type": panel_type,
            "title": title,
            "datasource": {"type": "postgres", "uid": datasource_uid},
            "gridPos": {"h": 12, "w": 24, "x": 0, "y": 0},
            "targets": [
                {
                    "refId": "A",
                    "format": "table",
                    "rawSql": self._build_deployment_plot_sql(
                        deployment_id=deployment_id,
                        plot_type=plot_type,
                        source=source,
                        field_path=field_path,
                        field_type=field_type,
                    ),
                    "editorMode": "code",
                }
            ],
            "options": options,
            "fieldConfig": field_config,
        }

    def _build_deployment_plot_sql(
        self,
        *,
        deployment_id: uuid.UUID,
        plot_type: DeploymentPlotType | str,
        source: DeploymentPlotSource | str,
        field_path: str | None,
        field_type: str | None,
    ) -> str:
        quoted_deployment_id = self._sql_string_literal(str(deployment_id))
        if plot_type == "latency":
            return (
                "SELECT timestamp AS time, latency_ms AS value "
                "FROM inference_log "
                f"WHERE deployment_id = {quoted_deployment_id} AND latency_ms IS NOT NULL AND $__timeFilter(timestamp) "
                "ORDER BY timestamp ASC"
            )
        if plot_type == "status_code":
            return (
                "SELECT CAST(status_code AS text) AS bucket, COUNT(*) AS value "
                "FROM inference_log "
                f"WHERE deployment_id = {quoted_deployment_id} AND status_code IS NOT NULL AND $__timeFilter(timestamp) "
                "GROUP BY status_code ORDER BY status_code ASC"
            )

        if source not in {"input", "output"} or not field_path:
            raise ValueError("custom deployment plots require a source and field path")

        json_column = "input_data" if source == "input" else "output_data"
        normalized_field_path = self._normalize_legacy_array_path(field_path, field_type)
        json_path_literal = self._jsonpath_literal(normalized_field_path)
        numeric_pattern = self._sql_string_literal(r"^-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?$")
        raw_value_expr = "values.value #>> '{}'"
        samples_from = (
            "FROM inference_log "
            f"CROSS JOIN LATERAL jsonb_path_query({json_column}, {json_path_literal}) AS values(value) "
        )

        if plot_type == "category_time_series":
            return (
                f"WITH samples AS (SELECT timestamp, {raw_value_expr} AS raw_value "
                f"{samples_from}"
                f"WHERE deployment_id = {quoted_deployment_id} AND $__timeFilter(timestamp)) "
                "SELECT $__timeGroup(timestamp, '1m') AS time, raw_value AS metric, COUNT(*) AS value "
                "FROM samples WHERE raw_value IS NOT NULL "
                "GROUP BY 1, 2 ORDER BY 1 ASC"
            )

        if plot_type == "distribution":
            value_filter = ""
            order_by = "value DESC, bucket ASC"
            if field_type in {"number", "number_array", "number_matrix", "number_matrix_index", None}:
                value_filter = f"AND raw_value ~ {numeric_pattern} "
                order_by = "CAST(raw_value AS double precision) ASC"
            return (
                f"WITH samples AS (SELECT {raw_value_expr} AS raw_value "
                f"{samples_from}"
                f"WHERE deployment_id = {quoted_deployment_id} AND $__timeFilter(timestamp)) "
                "SELECT raw_value AS bucket, COUNT(*) AS value FROM samples "
                f"WHERE raw_value IS NOT NULL {value_filter}"
                f"GROUP BY raw_value ORDER BY {order_by}"
            )

        return (
            f"WITH samples AS (SELECT timestamp, {raw_value_expr} AS raw_value "
            f"{samples_from}"
            f"WHERE deployment_id = {quoted_deployment_id} AND $__timeFilter(timestamp)) "
            "SELECT timestamp AS time, CAST(raw_value AS double precision) AS value FROM samples "
            f"WHERE raw_value ~ {numeric_pattern} "
            "ORDER BY timestamp ASC"
        )

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

    def _sql_path_literal(self, field_path: str) -> str:
        parts = [part for part in field_path.split(".") if part]
        escaped = ",".join(part.replace('"', '\\"').replace("\\", "\\\\") for part in parts)
        return f"'{{{escaped}}}'"

    def _normalize_legacy_array_path(self, field_path: str, field_type: str | None) -> str:
        if "[" in field_path:
            return field_path
        if field_type == "number_array":
            return f"{field_path}[*]"
        return field_path

    def _jsonpath_literal(self, field_path: str) -> str:
        path = "$"
        for segment in [part for part in field_path.split(".") if part]:
            name = ""
            index = 0
            while index < len(segment) and segment[index] != "[":
                name += segment[index]
                index += 1
            if name:
                path += self._jsonpath_property(name)
            while index < len(segment):
                if not segment.startswith("[", index):
                    raise ValueError(f"Invalid deployment plot field path: {field_path}")
                end = segment.find("]", index)
                if end == -1:
                    raise ValueError(f"Invalid deployment plot field path: {field_path}")
                selector = segment[index + 1:end]
                if selector == "*":
                    path += "[*]"
                elif selector.isdigit():
                    path += f"[{selector}]"
                else:
                    raise ValueError(f"Invalid deployment plot field path: {field_path}")
                index = end + 1
        return f"{self._sql_string_literal(path)}::jsonpath"

    def _jsonpath_property(self, name: str) -> str:
        if name.replace("_", "a").isalnum() and (name[0].isalpha() or name[0] == "_"):
            return f".{name}"
        escaped = name.replace("\\", "\\\\").replace('"', '\\"')
        return f'."{escaped}"'

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
