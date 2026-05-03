import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_MODEL = REPO_ROOT / "data-model.sql"
UUID_LITERAL = re.compile(
    r"'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'",
    re.IGNORECASE,
)


def _seed_section() -> str:
    sql = DATA_MODEL.read_text()
    return sql.split("-- ===================== Seed Data =============================", maxsplit=1)[1]


def test_status_lookup_tables_are_seeded_in_data_model():
    seed_sql = _seed_section()

    expected_status_tables = {
        "run_status": ("RUNNING", "COMPLETED", "FAILED"),
        "dataset_status": ("PENDING", "READY"),
        "model_status": ("PENDING", "READY"),
        "deployment_status": ("PENDING", "DEPLOYING", "ACTIVE", "FAILED", "DELETING", "DELETED"),
    }
    for table_name, statuses in expected_status_tables.items():
        assert f'INSERT INTO "{table_name}" ("id", "name") VALUES' in seed_sql
        for status in statuses:
            assert f"(gen_random_uuid(), '{status}')" in seed_sql


def test_seed_data_uses_postgres_uuid_generation():
    seed_sql = _seed_section()

    assert UUID_LITERAL.search(seed_sql) is None
    assert "gen_random_uuid()" in seed_sql
