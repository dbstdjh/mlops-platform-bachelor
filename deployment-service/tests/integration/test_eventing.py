import os

import pytest


@pytest.mark.asyncio
async def test_deployment_eventing_integration_is_opt_in():
    if os.getenv("RUN_DEPLOYMENT_SERVICE_DB_TESTS") != "1":
        pytest.skip("Set RUN_DEPLOYMENT_SERVICE_DB_TESTS=1 to run PostgreSQL LISTEN/NOTIFY worker tests")
