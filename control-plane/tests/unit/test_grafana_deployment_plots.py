import uuid

from src.infrastructure.observability.grafana import HttpGrafanaDashboardClient


def build_client() -> HttpGrafanaDashboardClient:
    return HttpGrafanaDashboardClient(
        grafana_url="http://grafana",
        public_url="http://grafana",
        admin_token="token",
        admin_user="admin",
        admin_password="admin",
        datasource_name="postgres",
        datasource_host="db",
        datasource_port=5432,
        datasource_database="mlops",
        datasource_user="mlops",
        datasource_password="mlops",
        datasource_sslmode="disable",
    )


def test_builds_default_deployment_latency_and_status_sql():
    client = build_client()
    deployment_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    latency_sql = client._build_deployment_plot_sql(
        deployment_id=deployment_id,
        plot_type="latency",
        source="system",
        field_path=None,
        field_type=None,
    )
    status_sql = client._build_deployment_plot_sql(
        deployment_id=deployment_id,
        plot_type="status_code",
        source="system",
        field_path=None,
        field_type=None,
    )

    assert "latency_ms AS value" in latency_sql
    assert "GROUP BY status_code" in status_sql
    assert str(deployment_id) in latency_sql


def test_builds_custom_input_distribution_sql_for_numeric_arrays():
    client = build_client()
    deployment_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    sql = client._build_deployment_plot_sql(
        deployment_id=deployment_id,
        plot_type="distribution",
        source="input",
        field_path="payload.features",
        field_type="number_array",
    )

    assert "jsonb_path_query(input_data, '$.payload.features[*]'::jsonpath)" in sql
    assert "COUNT(*) AS value" in sql


def test_builds_numeric_matrix_distribution_sql():
    client = build_client()
    deployment_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    sql = client._build_deployment_plot_sql(
        deployment_id=deployment_id,
        plot_type="distribution",
        source="input",
        field_path="instances[*][*]",
        field_type="number_matrix",
    )

    assert "jsonb_path_query(input_data, '$.instances[*][*]'::jsonpath)" in sql
    assert "raw_value ~" in sql
    assert "COUNT(*) AS value" in sql


def test_builds_numeric_matrix_index_time_series_sql():
    client = build_client()
    deployment_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    sql = client._build_deployment_plot_sql(
        deployment_id=deployment_id,
        plot_type="time_series",
        source="input",
        field_path="instances[*][0]",
        field_type="number_matrix_index",
    )

    assert "jsonb_path_query(input_data, '$.instances[*][0]'::jsonpath)" in sql
    assert "CAST(raw_value AS double precision) AS value" in sql
    assert "$__timeFilter(timestamp)" in sql


def test_builds_categorical_array_distribution_sql():
    client = build_client()
    deployment_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    sql = client._build_deployment_plot_sql(
        deployment_id=deployment_id,
        plot_type="distribution",
        source="output",
        field_path="predictions[*]",
        field_type="category_array",
    )

    assert "jsonb_path_query(output_data, '$.predictions[*]'::jsonpath)" in sql
    assert "raw_value ~" not in sql
    assert "GROUP BY raw_value" in sql


def test_builds_categorical_array_time_series_sql():
    client = build_client()
    deployment_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    sql = client._build_deployment_plot_sql(
        deployment_id=deployment_id,
        plot_type="category_time_series",
        source="output",
        field_path="predictions[*]",
        field_type="category_array",
    )

    assert "jsonb_path_query(output_data, '$.predictions[*]'::jsonpath)" in sql
    assert "$__timeGroup(timestamp, '1m') AS time" in sql
    assert "raw_value AS metric" in sql
