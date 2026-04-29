from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mldlc.models import RunInfo
from mldlc.run_context import RunContext


def build_run_info(status: str = "RUNNING") -> RunInfo:
    return RunInfo(
        experiment_slug="training",
        run_number=1,
        status=status,
        created_at=datetime.now(timezone.utc),
        ended_at=None,
        dataset=None,
        model=None,
        latest_metrics={},
        labels={},
    )


class FakeClient:
    def __init__(self) -> None:
        self.start_calls = 0
        self.append_calls = []
        self.complete_calls = 0
        self.fail_calls = 0

    def _start_run(self, experiment_slug, *, dataset=None, labels=None):
        self.start_calls += 1
        return build_run_info()

    def _append_run_steps(self, experiment_slug, run_number, items):
        self.append_calls.append((experiment_slug, run_number, items))

    def _complete_run(self, experiment_slug, run_number):
        self.complete_calls += 1
        return build_run_info(status="COMPLETED")

    def _fail_run(self, experiment_slug, run_number):
        self.fail_calls += 1
        return build_run_info(status="FAILED")

    def log_model(self, repository_slug, name, version, artifact, *, run=None, labels=None, serializer="auto"):
        return {"repository_slug": repository_slug, "version": version, "run": run.ref.model_dump()}


def test_run_context_completes_on_success():
    client = FakeClient()

    with RunContext(client, "training") as run:
        run.log_metric("loss", 0.4, step=1)

    assert client.start_calls == 1
    assert len(client.append_calls) == 1
    assert client.complete_calls == 1
    assert client.fail_calls == 0


def test_run_context_fails_on_exception():
    client = FakeClient()

    with pytest.raises(RuntimeError):
        with RunContext(client, "training"):
            raise RuntimeError("boom")

    assert client.start_calls == 1
    assert client.complete_calls == 0
    assert client.fail_calls == 1


def test_manual_completion_prevents_duplicate_terminal_transition():
    client = FakeClient()

    with RunContext(client, "training") as run:
        run.complete()

    assert client.complete_calls == 1
    assert client.fail_calls == 0

