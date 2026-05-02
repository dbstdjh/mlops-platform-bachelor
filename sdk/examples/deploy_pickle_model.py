from __future__ import annotations

import os
import pickle
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from mldlc import DeploymentInfo, MLDLC

load_dotenv()

IRIS_URL = "https://archive.ics.uci.edu/ml/machine-learning-databases/iris/iris.data"
IRIS_COLUMNS = [
    "sepal_length_cm",
    "sepal_width_cm",
    "petal_length_cm",
    "petal_width_cm",
    "species",
]
FEATURE_COLUMNS = IRIS_COLUMNS[:-1]
TERMINAL_FAILURE_STATUSES = {"FAILED", "DELETED"}


class IrisInput(BaseModel):
    instances: list[list[float]] = Field(
        examples=[[[5.1, 3.5, 1.4, 0.2]]],
        description="Rows of Iris features in sepal/petal order.",
    )


class IrisOutput(BaseModel):
    predictions: list[str]


@dataclass(frozen=True)
class TrainSplit:
    x_train: np.ndarray
    x_val: np.ndarray
    y_train: np.ndarray
    y_val: np.ndarray
    classes: np.ndarray


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
        ready_timeout=float(os.getenv("MLDLC_READY_TIMEOUT_SECONDS", "120")),
        poll_interval=float(os.getenv("MLDLC_POLL_INTERVAL_SECONDS", "2")),
    )


def fetch_iris() -> pd.DataFrame:
    dataframe = pd.read_csv(IRIS_URL, header=None, names=IRIS_COLUMNS)
    return dataframe.dropna().reset_index(drop=True)


def prepare_split(dataframe: pd.DataFrame) -> TrainSplit:
    x = dataframe[FEATURE_COLUMNS].to_numpy(dtype=np.float64)
    y = dataframe["species"].to_numpy()
    x_train, x_val, y_train, y_val = train_test_split(
        x,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )
    return TrainSplit(
        x_train=x_train,
        x_val=x_val,
        y_train=y_train,
        y_val=y_val,
        classes=np.unique(y),
    )


def train_logged_pipeline(run, split: TrainSplit, *, epochs: int = 25) -> Pipeline:
    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(split.x_train)
    x_val_scaled = scaler.transform(split.x_val)
    classifier = SGDClassifier(
        loss="log_loss",
        learning_rate="constant",
        eta0=0.01,
        random_state=42,
    )

    for epoch in range(1, epochs + 1):
        classifier.partial_fit(x_train_scaled, split.y_train, classes=split.classes)
        train_probabilities = classifier.predict_proba(x_train_scaled)
        val_probabilities = classifier.predict_proba(x_val_scaled)
        train_predictions = classifier.predict(x_train_scaled)
        val_predictions = classifier.predict(x_val_scaled)

        run.log_metrics(
            {
                "train_loss": float(log_loss(split.y_train, train_probabilities, labels=split.classes)),
                "val_loss": float(log_loss(split.y_val, val_probabilities, labels=split.classes)),
                "train_accuracy": float(accuracy_score(split.y_train, train_predictions)),
                "val_accuracy": float(accuracy_score(split.y_val, val_predictions)),
            },
            step=epoch,
        )

    return Pipeline([("scaler", scaler), ("classifier", classifier)])


def write_pickle(model: Pipeline, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        pickle.dump(model, handle)
    return destination


def wait_for_active_deployment(
    client: MLDLC,
    deployment_slug: str,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> DeploymentInfo:
    deadline = time.monotonic() + timeout_seconds
    while True:
        deployment = client.get_deployment(deployment_slug)
        print(f"Deployment {deployment.slug}: {deployment.status}")
        if deployment.status == "ACTIVE" and deployment.endpoint_url:
            return deployment
        if deployment.status in TERMINAL_FAILURE_STATUSES:
            raise RuntimeError(f"Deployment finished with status {deployment.status}")
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Deployment {deployment.slug} did not become ACTIVE within {timeout_seconds} seconds"
            )
        time.sleep(poll_interval_seconds)


def main() -> None:
    suffix = make_suffix()
    dataset_name = f"iris-deploy-dataset-{suffix}"
    experiment_name = f"iris-deploy-experiment-{suffix}"
    repository_name = f"iris-deploy-models-{suffix}"
    deployment_name = f"iris-deploy-{suffix}"
    timeout_seconds = float(os.getenv("MLDLC_DEPLOY_TIMEOUT_SECONDS", "300"))
    poll_interval_seconds = float(os.getenv("MLDLC_DEPLOY_POLL_INTERVAL_SECONDS", "5"))

    client = build_client()
    try:
        iris = fetch_iris()
        uploaded_dataset = client.upload_dataset(
            dataset_name,
            iris,
            file_type="parquet",
            labels={"dataset": "iris", "example": "deploy-pickle-model"},
        )

        with tempfile.TemporaryDirectory(prefix="mldlc-iris-deploy-") as temp_dir:
            parquet_path = client.download_dataset(
                uploaded_dataset.slug,
                uploaded_dataset.version,
                as_type="path",
                destination=Path(temp_dir) / "iris.parquet",
            )
            training_frame = pd.read_parquet(parquet_path)

            experiment = client.create_experiment(
                experiment_name,
                metrics=["train_loss", "val_loss", "train_accuracy", "val_accuracy"],
                labels={"dataset_slug": uploaded_dataset.slug, "example": "deploy-pickle-model"},
            )
            repository = client.create_repository(
                repository_name,
                labels={"dataset_slug": uploaded_dataset.slug, "example": "deploy-pickle-model"},
            )

            split = prepare_split(training_frame)
            with client.start_run(
                experiment.slug,
                dataset=uploaded_dataset,
                labels={"example": "deploy-pickle-model", "stage": "training"},
            ) as run:
                pipeline = train_logged_pipeline(run, split)
                model_path = write_pickle(pipeline, Path(temp_dir) / "iris-sgd-classifier.pkl")
                uploaded_model = run.log_model(
                    repository.slug,
                    "iris-sgd-classifier",
                    "1.0",
                    model_path,
                    labels={"algorithm": "sgd-logistic-regression", "example": "deploy-pickle-model"},
                )

            deployment = client.deploy_model(
                repository.slug,
                uploaded_model.version,
                deployment_name,
                input_schema=IrisInput,
                output_schema=IrisOutput,
                labels={"example": "deploy-pickle-model", "model": uploaded_model.name},
            )
            active = wait_for_active_deployment(
                client,
                deployment.slug,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )

        print("Iris deployment lifecycle finished successfully.")
        print(f"Dataset: {uploaded_dataset.slug} v{uploaded_dataset.version} file_type={uploaded_dataset.file_type}")
        print(f"Experiment: {experiment.slug}")
        print(f"Repository: {repository.slug}")
        print(f"Model: {uploaded_model.name} v{uploaded_model.version} status={uploaded_model.status}")
        print(f"Deployment: {active.slug} status={active.status}")
        print(f"Deployment URL: {active.endpoint_url}")
        print("Example curl:")
        print(build_curl(active.endpoint_url or "<DEPLOYMENT_URL>", client.access_token()))
    finally:
        client.close()


def build_curl(endpoint_url: str, access_token: str) -> str:
    return (
        "curl -X POST "
        f"'{endpoint_url}' "
        f"-H 'Authorization: Bearer {access_token}' "
        "-H 'Content-Type: application/json' "
        "--data '{\"instances\":[[5.1,3.5,1.4,0.2]]}'"
    )


if __name__ == "__main__":
    main()
