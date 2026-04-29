from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
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
    experiment_name = f"ui-long-history-experiment-{suffix}"
    total_steps = 250
    batch_size = 25

    client = build_client()
    try:
        experiment = client.create_experiment(
            experiment_name,
            metrics=["loss", "accuracy", "rolling_loss", "epoch_fraction"],
            labels={"example": "long-history-batched-steps", "batch_size": batch_size},
        )

        with client.start_run(
            experiment.slug,
            labels={"example": "long-history-batched-steps", "timestamp_mode": "explicit"},
        ) as run:
            started_at = datetime.now(timezone.utc)
            batch: list[dict[str, object]] = []

            for step in range(1, total_steps + 1):
                progress = step / total_steps
                loss = max(0.02, 1.6 / (1.0 + progress * 5.0) + 0.03 * math.sin(step / 8.0))
                rolling_loss = max(0.02, loss + 0.02 * math.cos(step / 11.0))
                accuracy = min(0.997, 0.47 + progress * 0.49)
                batch.append(
                    {
                        "step": step,
                        "logged_data": {
                            "loss": float(loss),
                            "accuracy": float(accuracy),
                            "rolling_loss": float(rolling_loss),
                            "epoch_fraction": float(progress),
                        },
                        "timestamp": started_at + timedelta(seconds=step * 5),
                    }
                )
                if len(batch) == batch_size:
                    run.log_batch(batch)
                    batch = []

            if batch:
                run.log_batch(batch)

        run_info = client.get_run(experiment.slug, 1)
        history = client.get_run_metric_history(experiment.slug, 1, "loss")
        assert len(history) == total_steps

        print("Created a long metric history using batched step uploads.")
        print(f"Experiment: {experiment.slug}")
        print(f"Run: #{run_info.run_number} status={run_info.status}")
        print(f"Total steps: {total_steps}")
        print(f"Batch size: {batch_size}")
        print(f"Batched requests: {total_steps // batch_size}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
