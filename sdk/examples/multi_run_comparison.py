from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pandas as pd
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


def build_dataset(row_count: int = 120) -> pd.DataFrame:
    index = np.arange(row_count, dtype=np.float64)
    seasonal = np.sin(index / 8.0)
    trend = index / row_count
    target = ((seasonal + trend) > 0.7).astype(int)
    return pd.DataFrame(
        {
            "feature_sin": seasonal,
            "feature_trend": trend,
            "feature_cos": np.cos(index / 11.0),
            "target": target,
        }
    )


def train_candidate(run, config: dict[str, float | str | bool], total_steps: int = 18) -> dict[str, float]:
    latest_metrics: dict[str, float] = {}
    learning_rate = float(config["learning_rate"])
    base_loss = float(config["base_loss"])
    decay = float(config["decay"])
    base_accuracy = float(config["base_accuracy"])
    accuracy_gain = float(config["accuracy_gain"])
    val_gap = float(config["val_gap"])
    f1_gap = float(config["f1_gap"])

    for step in range(1, total_steps + 1):
        progress = step / total_steps
        train_loss = max(0.03, base_loss * math.exp(-decay * progress * 3.0) + 0.01 * math.sin(step / 2.0))
        val_loss = max(train_loss + val_gap + 0.01 * math.cos(step / 3.0), 0.04)
        accuracy = min(0.995, base_accuracy + accuracy_gain * progress)
        f1 = max(0.0, min(0.995, accuracy - f1_gap + 0.005 * math.sin(step / 5.0)))
        step_learning_rate = learning_rate * (0.92 ** (step - 1))

        latest_metrics = {
            "train_loss": float(train_loss),
            "val_loss": float(val_loss),
            "accuracy": float(accuracy),
            "f1": float(f1),
            "learning_rate": float(step_learning_rate),
        }
        run.log_metrics(latest_metrics, step=step)

    return latest_metrics


def main() -> None:
    suffix = make_suffix()
    dataset_name = f"ui-multi-run-dataset-{suffix}"
    experiment_name = f"ui-multi-run-experiment-{suffix}"
    repository_name = f"ui-multi-run-models-{suffix}"

    run_configs: list[dict[str, float | str | bool]] = [
        {
            "name": "baseline",
            "learning_rate": 0.08,
            "base_loss": 1.15,
            "decay": 0.90,
            "base_accuracy": 0.58,
            "accuracy_gain": 0.33,
            "val_gap": 0.06,
            "f1_gap": 0.03,
            "attach_model": True,
        },
        {
            "name": "low-lr-stable",
            "learning_rate": 0.03,
            "base_loss": 1.28,
            "decay": 0.72,
            "base_accuracy": 0.56,
            "accuracy_gain": 0.28,
            "val_gap": 0.04,
            "f1_gap": 0.02,
            "attach_model": False,
        },
        {
            "name": "fast-converge",
            "learning_rate": 0.14,
            "base_loss": 1.00,
            "decay": 1.05,
            "base_accuracy": 0.60,
            "accuracy_gain": 0.31,
            "val_gap": 0.08,
            "f1_gap": 0.04,
            "attach_model": True,
        },
    ]

    client = build_client()
    try:
        dataset = client.upload_dataset(
            dataset_name,
            build_dataset(),
            labels={"example": "multi-run-comparison", "shape": "tabular"},
        )
        experiment = client.create_experiment(
            experiment_name,
            metrics=["train_loss", "val_loss", "accuracy", "f1", "learning_rate"],
            labels={"example": "multi-run-comparison", "dataset_slug": dataset.slug},
        )
        repository = client.create_repository(
            repository_name,
            labels={"example": "multi-run-comparison", "experiment_slug": experiment.slug},
        )

        for config in run_configs:
            run_name = str(config["name"])
            with client.start_run(
                experiment.slug,
                dataset=dataset,
                labels={
                    "example": "multi-run-comparison",
                    "candidate": run_name,
                    "learning_rate": config["learning_rate"],
                },
            ) as run:
                latest_metrics = train_candidate(run, config)
                if bool(config["attach_model"]):
                    run.log_model(
                        repository.slug,
                        f"{run_name}-classifier",
                        f"{run_name}-1.0",
                        {
                            "candidate": run_name,
                            "final_metrics": latest_metrics,
                            "weights": [round(latest_metrics["accuracy"], 4), round(latest_metrics["f1"], 4)],
                        },
                        labels={"example": "multi-run-comparison", "candidate": run_name},
                    )

        runs = client.list_runs(experiment.slug)
        val_history = client.get_experiment_metric_history(experiment.slug, "val_loss")
        assert len(runs) == len(run_configs)
        assert len(val_history) == len(run_configs) * 18

        print("Created a comparison-friendly experiment with multiple runs.")
        print(f"Dataset: {dataset.slug} v{dataset.version}")
        print(f"Experiment: {experiment.slug}")
        print(f"Repository: {repository.slug}")
        for run in runs:
            model_ref = "none" if run.model is None else f"{run.model.repository_slug}:{run.model.version}"
            print(
                f"Run #{run.run_number} status={run.status} "
                f"candidate={run.labels.get('candidate')} model={model_ref}"
            )
    finally:
        client.close()


if __name__ == "__main__":
    main()
