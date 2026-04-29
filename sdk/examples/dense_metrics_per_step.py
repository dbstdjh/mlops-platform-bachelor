from __future__ import annotations

import math
import os
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


def build_metrics(step: int, total_steps: int) -> dict[str, float]:
    progress = step / total_steps
    train_loss = max(0.03, 1.35 * math.exp(-3.2 * progress) + 0.01 * math.sin(step / 2.0))
    val_loss = max(0.05, train_loss + 0.05 + 0.015 * math.cos(step / 3.0))
    accuracy = min(0.996, 0.51 + progress * 0.43)
    precision = min(0.995, accuracy - 0.01 + 0.01 * math.sin(step / 6.0))
    recall = min(0.995, accuracy - 0.015 + 0.008 * math.cos(step / 4.0))
    f1 = max(0.0, 2 * precision * recall / (precision + recall))
    learning_rate = 0.08 * (0.96 ** (step - 1))
    grad_norm = max(0.12, 4.8 * math.exp(-2.5 * progress))
    weight_norm = 1.2 + progress * 0.7
    batch_time_ms = 190.0 - progress * 45.0 + 2.0 * math.sin(step / 3.0)
    throughput_rows_per_sec = 950.0 + progress * 420.0 + 10.0 * math.cos(step / 5.0)
    memory_gb = 1.8 + 0.25 * math.sin(step / 7.0)

    return {
        "train_loss": float(train_loss),
        "val_loss": float(val_loss),
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "learning_rate": float(learning_rate),
        "grad_norm": float(grad_norm),
        "weight_norm": float(weight_norm),
        "batch_time_ms": float(batch_time_ms),
        "throughput_rows_per_sec": float(throughput_rows_per_sec),
        "memory_gb": float(memory_gb),
    }


def main() -> None:
    suffix = make_suffix()
    experiment_name = f"ui-dense-metrics-experiment-{suffix}"
    metric_names = list(build_metrics(1, 40).keys())

    client = build_client()
    try:
        experiment = client.create_experiment(
            experiment_name,
            metrics=metric_names,
            labels={"example": "dense-metrics-per-step", "dataset_attached": False},
        )
        print(experiment.slug)
        with client.start_run(
            experiment.slug,
            labels={"example": "dense-metrics-per-step", "notes": "no-dataset-no-model"},
        ) as run:
            for step in range(1, 41):
                run.log_metrics(build_metrics(step, 40), step=step)

        run_info = client.get_run(experiment.slug, 1)
        precision_history = client.get_run_metric_history(experiment.slug, 1, "precision")
        assert len(precision_history) == 40

        print("Created a run with lots of metrics at every step.")
        print(f"Experiment: {experiment.slug}")
        print(f"Run: #{run_info.run_number} status={run_info.status}")
        print(f"Metrics per step: {len(metric_names)}")
        print(f"Dataset linked: {run_info.dataset is not None}")
        print(f"Model linked: {run_info.model is not None}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
