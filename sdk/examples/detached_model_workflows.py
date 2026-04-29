from __future__ import annotations

import math
import os
import pickle
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv

from mldlc import MLDLC

load_dotenv()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def make_suffix() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{timestamp}-{uuid4().hex[:8]}"


def build_client() -> MLDLC:
    return MLDLC(
        username=require_env("MLDLC_USERNAME"),
        api_key=require_env("MLDLC_API_KEY"),
        base_url=os.getenv("MLDLC_BASE_URL", "http://localhost:8000"),
    )


def main() -> None:
    suffix = make_suffix()
    experiment_name = f"ui-detached-model-experiment-{suffix}"
    repository_name = f"ui-detached-model-repository-{suffix}"

    client = build_client()
    try:
        experiment = client.create_experiment(
            experiment_name,
            metrics=["loss", "accuracy"],
            labels={"example": "detached-model-workflows"},
        )
        repository = client.create_repository(
            repository_name,
            labels={"example": "detached-model-workflows", "linking_mode": "mixed"},
        )

        with client.start_run(
            experiment.slug,
            labels={"example": "detached-model-workflows", "model_logged_inside_run": False},
        ) as run:
            for step in range(1, 13):
                progress = step / 12.0
                loss = max(0.05, 1.1 * math.exp(-2.5 * progress) + 0.01 * math.sin(step))
                accuracy = min(0.992, 0.55 + progress * 0.36)
                run.log_metrics({"loss": float(loss), "accuracy": float(accuracy)}, step=step)

        completed_run = client.get_run(experiment.slug, 1)
        linked_model = client.log_model(
            repository.slug,
            "post-run-linked-model",
            "linked-after-run-1.0",
            {
                "kind": "late-linked",
                "source_run": completed_run.model_dump(),
                "weights": [0.12, 0.48, 0.91],
            },
            run=completed_run,
            labels={"example": "detached-model-workflows", "linking_mode": "after-run"},
        )
        standalone_model = client.log_model(
            repository.slug,
            "standalone-model",
            "standalone-1.0",
            {
                "kind": "standalone",
                "notes": "uploaded without any run reference",
                "weights": [0.33, 0.27, 0.40],
            },
            labels={"example": "detached-model-workflows", "linking_mode": "none"},
        )

        refreshed_run = client.get_run(experiment.slug, 1)
        restored_linked_model = client.download_model(
            repository.slug,
            linked_model.version,
            loader=lambda path: pickle.loads(path.read_bytes()),
        )
        restored_standalone_model = client.download_model(
            repository.slug,
            standalone_model.version,
            loader=lambda path: pickle.loads(path.read_bytes()),
        )

        assert linked_model.run is not None
        assert linked_model.run.run_number == completed_run.run_number
        assert standalone_model.run is None
        assert refreshed_run.model is not None
        assert restored_linked_model["kind"] == "late-linked"
        assert restored_standalone_model["kind"] == "standalone"

        print("Created detached model-registration scenarios.")
        print(f"Experiment: {experiment.slug}")
        print(f"Repository: {repository.slug}")
        print(f"Run #{refreshed_run.run_number} model link: {refreshed_run.model.repository_slug}:{refreshed_run.model.version}")
        print(f"Linked-after-run model: {linked_model.version} run={linked_model.run.model_dump()}")
        print(f"Standalone model: {standalone_model.version} run={standalone_model.run}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
