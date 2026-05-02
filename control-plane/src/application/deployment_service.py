"""Application service: model deployments."""

import uuid
from typing import Any

from src.core.entities.dashboard import (
    Dashboard,
    DeploymentDashboardCreate,
    DeploymentDashboardResponse,
    DeploymentPlotField,
    DeploymentPlotType,
)
from src.core.entities.deployment import (
    Deployment,
    DeploymentCreate,
    DeploymentResponse,
    DeploymentTask,
    FileDeployment,
)
from src.core.entities.pagination import PaginatedResponse, SortDirection, page_items
from src.core.entities.resource import Resource
from src.core.ports.observability import GrafanaDashboardClient
from src.core.ports.repositories import (
    DashboardRepo,
    DeploymentRepo,
    DeploymentTaskRepo,
    ModelRepo,
    ModelRepositoryRepo,
    ResourceRepository,
)
from src.core.slugging import slug_candidate, slugify


PLOT_TYPES_BY_VALUE_TYPE: dict[str, list[DeploymentPlotType]] = {
    "number": ["time_series", "distribution"],
    "number_array": ["time_series", "distribution"],
    "number_matrix": ["distribution"],
    "number_matrix_index": ["time_series", "distribution"],
    "category": ["distribution", "category_time_series"],
    "category_array": ["distribution", "category_time_series"],
    "boolean": ["distribution", "category_time_series"],
    "boolean_array": ["distribution", "category_time_series"],
}


class DeploymentService:
    """Application service for asynchronous model deployment requests."""

    def __init__(
        self,
        deployment_repo: DeploymentRepo,
        deployment_task_repo: DeploymentTaskRepo,
        model_repo_repo: ModelRepositoryRepo,
        model_repo: ModelRepo,
        resource_repo: ResourceRepository,
        dashboard_repo: DashboardRepo | None = None,
        grafana_client: GrafanaDashboardClient | None = None,
    ):
        self._deployment_repo = deployment_repo
        self._deployment_task_repo = deployment_task_repo
        self._model_repo_repo = model_repo_repo
        self._model_repo = model_repo
        self._resource_repo = resource_repo
        self._dashboard_repo = dashboard_repo
        self._grafana_client = grafana_client

    async def create_model_deployment(
        self,
        user_id: uuid.UUID,
        repository_slug: str,
        version: str,
        data: DeploymentCreate,
    ) -> DeploymentResponse:
        """Create a deployment record and enqueue a deployment task."""
        repo = await self._model_repo_repo.get_by_slug(user_id, repository_slug)
        if not repo:
            raise ValueError(f"Model repository '{repository_slug}' not found")

        model = await self._model_repo.get_ready_by_version(repo.id, version)
        if not model:
            raise ValueError("No READY model found with that version")
        if model.file_type != "pickle":
            raise ValueError("Only pickle model deployments are supported in V1")

        if await self._deployment_repo.name_exists(user_id, data.name):
            raise FileExistsError(f"Deployment '{data.name}' already exists")

        slug = await self._generate_unique_slug(user_id, data.name)
        resource = Resource(labels=data.labels)
        await self._resource_repo.create(resource)

        deployment = Deployment(
            user_id=user_id,
            resource_id=resource.id,
            name=data.name,
            slug=slug,
            input_schema=data.input_schema,
            output_schema=data.output_schema,
            status="PENDING",
        )
        await self._deployment_repo.create_file_deployment(
            deployment,
            FileDeployment(id=deployment.id, model_id=model.id),
        )
        await self._deployment_task_repo.create(
            DeploymentTask(deployment_id=deployment.id, type="DEPLOY")
        )

        return await self._build_response(deployment)

    async def list_deployments(self, user_id: uuid.UUID) -> list[DeploymentResponse]:
        deployments = await self._deployment_repo.list_by_user(user_id)
        return [await self._build_response(deployment) for deployment in deployments]

    async def list_deployments_page(
        self,
        user_id: uuid.UUID,
        *,
        search: str | None,
        sort_by: str,
        sort_dir: SortDirection,
        limit: int,
        offset: int,
    ) -> PaginatedResponse[DeploymentResponse]:
        """List deployments with dashboard-oriented filtering and pagination."""
        return page_items(
            await self.list_deployments(user_id),
            search=search,
            search_fields=[
                lambda item: item.name,
                lambda item: item.slug,
                lambda item: item.status,
                lambda item: item.source_type,
                lambda item: item.image_ref,
                lambda item: item.endpoint_url,
            ],
            sort_by=sort_by,
            sort_dir=sort_dir,
            sort_fields={
                "name": lambda item: item.name,
                "slug": lambda item: item.slug,
                "status": lambda item: item.status,
                "source_type": lambda item: item.source_type,
                "created_at": lambda item: item.created_at,
            },
            limit=limit,
            offset=offset,
        )

    async def get_deployment(self, user_id: uuid.UUID, deployment_slug: str) -> DeploymentResponse | None:
        deployment = await self._deployment_repo.get_by_slug(user_id, deployment_slug)
        if not deployment:
            return None
        return await self._build_response(deployment)

    async def delete_deployment(self, user_id: uuid.UUID, deployment_slug: str) -> DeploymentResponse | None:
        deployment = await self._deployment_repo.get_by_slug(user_id, deployment_slug)
        if not deployment:
            return None

        if deployment.status != "DELETED":
            updated = await self._deployment_repo.update_status(deployment.id, "DELETING")
            deployment = updated or deployment.model_copy(update={"status": "DELETING"})
            await self._deployment_task_repo.create(
                DeploymentTask(deployment_id=deployment.id, type="DELETE")
            )

        return await self._build_response(deployment)

    async def purge_deployment(self, user_id: uuid.UUID, deployment_slug: str) -> bool:
        """Permanently remove a deployment record and dependent observability data."""
        return await self._deployment_repo.hard_delete(user_id, deployment_slug)

    async def list_deployment_dashboards(
        self,
        user_id: uuid.UUID,
        deployment_slug: str,
    ) -> list[DeploymentDashboardResponse]:
        deployment = await self._get_deployment_or_raise(user_id, deployment_slug)
        dashboard_repo = self._require_dashboard_repo()
        await self._ensure_default_deployment_dashboards(deployment)
        dashboards = await dashboard_repo.list_by_deployment(deployment.id)
        return [self._build_deployment_dashboard_response(item) for item in dashboards]

    async def create_deployment_dashboard(
        self,
        user_id: uuid.UUID,
        deployment_slug: str,
        data: DeploymentDashboardCreate,
    ) -> DeploymentDashboardResponse:
        deployment = await self._get_deployment_or_raise(user_id, deployment_slug)
        field = self._get_plot_field_or_raise(deployment, data.source, data.field_path)
        if data.plot_type not in field.plot_types:
            raise ValueError(f"Plot type '{data.plot_type}' is not available for field '{data.field_path}'")
        created = await self._create_deployment_dashboard(
            deployment,
            title=data.title,
            plot_type=data.plot_type,
            source=data.source,
            field_path=data.field_path,
            field_type=field.value_type,
            is_system_locked=False,
        )
        return self._build_deployment_dashboard_response(created)

    async def delete_deployment_dashboard(
        self,
        user_id: uuid.UUID,
        deployment_slug: str,
        dashboard_id: uuid.UUID,
    ) -> None:
        deployment = await self._get_deployment_or_raise(user_id, deployment_slug)
        dashboard_repo = self._require_dashboard_repo()
        grafana_client = self._require_grafana_client()
        existing = await dashboard_repo.get_by_id_for_deployment(deployment.id, dashboard_id)
        if not existing:
            raise ValueError("Deployment dashboard not found")
        if existing.is_system_locked:
            raise ValueError("System deployment dashboards cannot be deleted")

        if existing.grafana_uid:
            await grafana_client.delete_dashboard(existing.grafana_uid)
        deleted = await dashboard_repo.delete_deployment_dashboard(deployment.id, dashboard_id)
        if not deleted:
            raise ValueError("Deployment dashboard not found")

    async def list_plot_fields(
        self,
        user_id: uuid.UUID,
        deployment_slug: str,
    ) -> list[DeploymentPlotField]:
        deployment = await self._get_deployment_or_raise(user_id, deployment_slug)
        return self._extract_plot_fields(deployment)

    async def _build_response(self, deployment: Deployment) -> DeploymentResponse:
        resource = await self._resource_repo.get_by_id(deployment.resource_id)
        labels = resource.labels if resource else {}
        image_ref = await self._deployment_repo.get_image_ref(deployment.id)
        return DeploymentResponse(
            name=deployment.name,
            slug=deployment.slug,
            status=deployment.status,
            endpoint_url=deployment.endpoint_url,
            input_schema=deployment.input_schema,
            output_schema=deployment.output_schema,
            created_at=deployment.created_at,
            labels=labels,
            source_type="image" if image_ref else "file",
            image_ref=image_ref,
        )

    async def _get_deployment_or_raise(self, user_id: uuid.UUID, deployment_slug: str) -> Deployment:
        deployment = await self._deployment_repo.get_by_slug(user_id, deployment_slug)
        if not deployment:
            raise ValueError("Deployment not found")
        return deployment

    async def _ensure_default_deployment_dashboards(self, deployment: Deployment) -> None:
        dashboard_repo = self._require_dashboard_repo()
        existing = await dashboard_repo.list_by_deployment(deployment.id)
        existing_system_plots = {
            str(item.plot_type)
            for item in existing
            if item.is_system_locked and item.source == "system"
        }
        defaults = [
            ("latency", "Latency", "latency_ms over time"),
            ("status_code", "Status codes", "HTTP status code distribution"),
        ]
        for plot_type, title, field_path in defaults:
            if plot_type in existing_system_plots:
                continue
            await self._create_deployment_dashboard(
                deployment,
                title=title,
                plot_type=plot_type,
                source="system",
                field_path=field_path,
                field_type=None,
                is_system_locked=True,
            )

    async def _create_deployment_dashboard(
        self,
        deployment: Deployment,
        *,
        title: str,
        plot_type: str,
        source: str,
        field_path: str | None,
        field_type: str | None,
        is_system_locked: bool,
    ):
        dashboard_repo = self._require_dashboard_repo()
        grafana_client = self._require_grafana_client()
        grafana_uid = await grafana_client.upsert_deployment_plot(
            grafana_uid=None,
            title=title,
            deployment_id=deployment.id,
            plot_type=plot_type,
            source=source,
            field_path=field_path,
            field_type=field_type,
        )
        dashboard = Dashboard(
            name=title,
            kind="DEPLOYMENT_PLOT",
            grafana_uid=grafana_uid,
            is_system_locked=is_system_locked,
            config_data={
                "plot_type": plot_type,
                "source": source,
                "field_path": field_path,
                "field_type": field_type,
            },
        )
        try:
            return await dashboard_repo.create_deployment_dashboard(dashboard, deployment_id=deployment.id)
        except Exception:
            await grafana_client.delete_dashboard(grafana_uid)
            raise

    def _build_deployment_dashboard_response(self, item) -> DeploymentDashboardResponse:
        grafana_client = self._require_grafana_client()
        return DeploymentDashboardResponse(
            id=item.id,
            title=item.title,
            plot_type=str(item.plot_type),
            source=str(item.source),
            field_path=item.field_path,
            is_system_locked=item.is_system_locked,
            iframe_url=grafana_client.build_solo_iframe_url(item.grafana_uid or ""),
            created_at=item.created_at,
        )

    def _extract_plot_fields(self, deployment: Deployment) -> list[DeploymentPlotField]:
        fields_by_key: dict[tuple[str, str], DeploymentPlotField] = {}
        for source, schema in (("input", deployment.input_schema), ("output", deployment.output_schema)):
            root_schema = schema or {}
            for field in self._extract_schema_fields(source, root_schema, root_schema):
                fields_by_key[(field.source, field.path)] = field
        return sorted(fields_by_key.values(), key=lambda item: (item.source, item.path))

    def _extract_schema_fields(
        self,
        source: str,
        schema: dict[str, Any],
        root_schema: dict[str, Any],
        prefix: str = "",
    ) -> list[DeploymentPlotField]:
        schema = self._normalize_schema(schema, root_schema)
        if not schema:
            return []

        branch_fields = self._extract_branch_fields(source, schema, root_schema, prefix)
        if branch_fields is not None:
            return branch_fields

        schema_type = self._schema_type(schema)
        if prefix and schema_type in {"number", "integer"}:
            return [self._plot_field(source, prefix, "number")]
        if prefix and self._is_categorical_scalar(schema):
            return [self._plot_field(source, prefix, "boolean" if schema_type == "boolean" else "category")]
        if schema_type == "array" and prefix:
            return self._extract_array_fields(source, schema, root_schema, prefix)

        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return []

        fields: list[DeploymentPlotField] = []
        for name, subschema in properties.items():
            if not isinstance(subschema, dict):
                continue
            path = f"{prefix}.{name}" if prefix else str(name)
            fields.extend(self._extract_schema_fields(source, subschema, root_schema, path))
        return fields

    def _extract_array_fields(
        self,
        source: str,
        schema: dict[str, Any],
        root_schema: dict[str, Any],
        prefix: str,
    ) -> list[DeploymentPlotField]:
        items = schema.get("items")
        if not isinstance(items, dict):
            prefix_items = schema.get("prefixItems")
            if isinstance(prefix_items, list):
                fields: list[DeploymentPlotField] = []
                for index, item_schema in enumerate(prefix_items):
                    if isinstance(item_schema, dict):
                        fields.extend(
                            self._extract_schema_fields(source, item_schema, root_schema, f"{prefix}[{index}]")
                        )
                return fields
            return []

        items = self._normalize_schema(items, root_schema)
        item_type = self._schema_type(items)
        if item_type in {"number", "integer"}:
            return [self._plot_field(source, f"{prefix}[*]", "number_array")]
        if self._is_categorical_scalar(items):
            value_type = "boolean_array" if item_type == "boolean" else "category_array"
            return [self._plot_field(source, f"{prefix}[*]", value_type)]
        if item_type == "array":
            nested_items = self._normalize_schema(items.get("items") or {}, root_schema)
            nested_type = self._schema_type(nested_items)
            if nested_type in {"number", "integer"}:
                fields = [self._plot_field(source, f"{prefix}[*][*]", "number_matrix")]
                width = self._fixed_array_length(items)
                if width is not None:
                    fields.extend(
                        self._plot_field(source, f"{prefix}[*][{index}]", "number_matrix_index")
                        for index in range(width)
                    )
                return fields
            if self._is_categorical_scalar(nested_items):
                value_type = "boolean_array" if nested_type == "boolean" else "category_array"
                return [self._plot_field(source, f"{prefix}[*][*]", value_type)]

        return self._extract_schema_fields(source, items, root_schema, f"{prefix}[*]")

    def _extract_branch_fields(
        self,
        source: str,
        schema: dict[str, Any],
        root_schema: dict[str, Any],
        prefix: str,
    ) -> list[DeploymentPlotField] | None:
        branch_key = "anyOf" if isinstance(schema.get("anyOf"), list) else "oneOf" if isinstance(schema.get("oneOf"), list) else None
        if branch_key is None:
            return None
        fields: dict[tuple[str, str], DeploymentPlotField] = {}
        for branch in schema[branch_key]:
            if not isinstance(branch, dict) or self._is_null_schema(branch):
                continue
            for field in self._extract_schema_fields(source, branch, root_schema, prefix):
                fields[(field.source, field.path)] = field
        return list(fields.values())

    def _normalize_schema(self, schema: dict[str, Any], root_schema: dict[str, Any]) -> dict[str, Any]:
        schema = self._resolve_ref(schema, root_schema)
        schema_type = schema.get("type")
        if isinstance(schema_type, list):
            non_null_types = [item for item in schema_type if item != "null"]
            if len(non_null_types) == 1:
                schema = {**schema, "type": non_null_types[0]}
        for branch_key in ("anyOf", "oneOf"):
            branches = schema.get(branch_key)
            if isinstance(branches, list):
                non_null = [branch for branch in branches if isinstance(branch, dict) and not self._is_null_schema(branch)]
                if len(non_null) == 1:
                    return self._normalize_schema(non_null[0], root_schema)
        return schema

    def _resolve_ref(self, schema: dict[str, Any], root_schema: dict[str, Any]) -> dict[str, Any]:
        ref = schema.get("$ref")
        if not isinstance(ref, str) or not ref.startswith("#/"):
            return schema

        node: Any = root_schema
        for part in ref[2:].split("/"):
            key = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict) or key not in node:
                return schema
            node = node[key]
        if not isinstance(node, dict):
            return schema
        merged = {**node, **{key: value for key, value in schema.items() if key != "$ref"}}
        return merged

    def _schema_type(self, schema: dict[str, Any]) -> str | None:
        schema_type = schema.get("type")
        if isinstance(schema_type, str):
            return schema_type
        if isinstance(schema.get("enum"), list):
            enum_values = [value for value in schema["enum"] if value is not None]
            if enum_values and all(isinstance(value, bool) for value in enum_values):
                return "boolean"
            if enum_values and all(isinstance(value, str) for value in enum_values):
                return "string"
        return None

    def _is_categorical_scalar(self, schema: dict[str, Any]) -> bool:
        return self._schema_type(schema) in {"string", "boolean"}

    def _is_null_schema(self, schema: dict[str, Any]) -> bool:
        return schema.get("type") == "null"

    def _fixed_array_length(self, schema: dict[str, Any]) -> int | None:
        prefix_items = schema.get("prefixItems")
        if isinstance(prefix_items, list) and prefix_items:
            return len(prefix_items)
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if isinstance(min_items, int) and isinstance(max_items, int) and min_items == max_items:
            return min_items
        return None

    def _plot_field(self, source: str, path: str, value_type: str) -> DeploymentPlotField:
        return DeploymentPlotField(
            source=source,
            path=path,
            value_type=value_type,
            plot_types=PLOT_TYPES_BY_VALUE_TYPE[value_type],
        )

    def _get_plot_field_or_raise(self, deployment: Deployment, source: str, field_path: str) -> DeploymentPlotField:
        for field in self._extract_plot_fields(deployment):
            if field.source == source and field.path == field_path:
                return field
        raise ValueError("Requested plot field is not available")

    def _require_dashboard_repo(self) -> DashboardRepo:
        if self._dashboard_repo is None:
            raise RuntimeError("Deployment dashboard repository is not configured")
        return self._dashboard_repo

    def _require_grafana_client(self) -> GrafanaDashboardClient:
        if self._grafana_client is None:
            raise RuntimeError("Grafana client is not configured")
        return self._grafana_client

    async def _generate_unique_slug(self, user_id: uuid.UUID, name: str) -> str:
        base_slug = slugify(name)
        index = 1
        while True:
            candidate = slug_candidate(base_slug, index)
            if not await self._deployment_repo.slug_exists(user_id, candidate):
                return candidate
            index += 1
