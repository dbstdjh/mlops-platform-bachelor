from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from mldlc.models import RunInfo, RunRef

if TYPE_CHECKING:
    from mldlc.client import MLDLC


class RunContext:
    """MLflow-like run context that prevents zombie runs."""

    def __init__(
        self,
        client: "MLDLC",
        experiment_slug: str,
        *,
        dataset=None,
        labels: dict[str, Any] | None = None,
    ) -> None:
        self._client = client
        self._experiment_slug = experiment_slug
        self._dataset = dataset
        self._labels = labels or {}
        self._run: RunInfo | None = None
        self._terminal = False

    @property
    def info(self) -> RunInfo:
        self._ensure_started()
        return self._run

    @property
    def experiment_slug(self) -> str:
        return self.info.experiment_slug

    @property
    def run_number(self) -> int:
        return self.info.run_number

    @property
    def ref(self) -> RunRef:
        return RunRef(experiment_slug=self.experiment_slug, run_number=self.run_number)

    def _ensure_started(self) -> None:
        if self._run is None:
            self._run = self._client._start_run(  # noqa: SLF001 - tight coupling by design
                self._experiment_slug,
                dataset=self._dataset,
                labels=self._labels,
            )

    def log_metric(
        self,
        name: str,
        value: float,
        *,
        step: int,
        timestamp: datetime | str | None = None,
    ) -> None:
        self.log_metrics({name: value}, step=step, timestamp=timestamp)

    def log_metrics(
        self,
        metrics: dict[str, float | int],
        *,
        step: int,
        timestamp: datetime | str | None = None,
    ) -> None:
        self.log_batch([{"step": step, "logged_data": metrics, "timestamp": timestamp}])

    def log_batch(self, items: list[dict[str, Any]]) -> None:
        self._ensure_started()
        self._client._append_run_steps(self.experiment_slug, self.run_number, items)  # noqa: SLF001

    def log_model(
        self,
        repository_slug: str,
        name: str,
        version: str,
        artifact,
        *,
        labels: dict[str, Any] | None = None,
        serializer: str = "auto",
        file_name: str | None = None,
    ):
        self._ensure_started()
        return self._client.log_model(  # noqa: SLF001
            repository_slug,
            name,
            version,
            artifact,
            run=self,
            labels=labels,
            serializer=serializer,
            file_name=file_name,
        )

    def complete(self) -> RunInfo:
        self._ensure_started()
        if not self._terminal:
            self._run = self._client._complete_run(self.experiment_slug, self.run_number)  # noqa: SLF001
            self._terminal = True
        return self._run

    def fail(self) -> RunInfo:
        self._ensure_started()
        if not self._terminal:
            self._run = self._client._fail_run(self.experiment_slug, self.run_number)  # noqa: SLF001
            self._terminal = True
        return self._run

    def __enter__(self) -> "RunContext":
        self._ensure_started()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self.complete()
        else:
            self.fail()
        return False
