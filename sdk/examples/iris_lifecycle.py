from __future__ import annotations

import os
import pickle
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from mldlc import MLDLC

load_dotenv()

IRIS_URL = "https://archive.ics.uci.edu/ml/machine-learning-databases/iris/iris.data"
IRIS_COLUMNS = [
    "sepal_length_cm",
    "sepal_width_cm",
    "petal_length_cm",
    "petal_width_cm",
    "species",
]


@dataclass
class SplitData:
    x_train: np.ndarray
    y_train: np.ndarray
    x_val: np.ndarray
    y_val: np.ndarray
    feature_names: list[str]
    classes: list[str]
    mean: np.ndarray
    std: np.ndarray


def fetch_iris_from_internet() -> pd.DataFrame:
    dataframe = pd.read_csv(IRIS_URL, header=None, names=IRIS_COLUMNS)
    dataframe = dataframe.dropna().reset_index(drop=True)
    return dataframe


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exponent = np.exp(shifted)
    return exponent / exponent.sum(axis=1, keepdims=True)


def accuracy(logits: np.ndarray, y_true: np.ndarray) -> float:
    predictions = logits.argmax(axis=1)
    return float((predictions == y_true).mean())


def cross_entropy(probabilities: np.ndarray, y_true: np.ndarray) -> float:
    chosen = probabilities[np.arange(len(y_true)), y_true]
    return float(-np.log(chosen + 1e-12).mean())


def prepare_training_data(dataframe: pd.DataFrame, *, seed: int = 42, validation_fraction: float = 0.2) -> SplitData:
    features = dataframe.drop(columns=["species"])
    labels = dataframe["species"]

    class_names = sorted(labels.unique().tolist())
    class_to_index = {name: index for index, name in enumerate(class_names)}
    y = labels.map(class_to_index).to_numpy(dtype=np.int64)
    x = features.to_numpy(dtype=np.float64)

    rng = np.random.default_rng(seed)
    train_indices: list[np.ndarray] = []
    val_indices: list[np.ndarray] = []
    for class_index in range(len(class_names)):
        indices = np.where(y == class_index)[0]
        shuffled = rng.permutation(indices)
        split_point = int(len(shuffled) * (1 - validation_fraction))
        train_indices.append(shuffled[:split_point])
        val_indices.append(shuffled[split_point:])

    train_index = rng.permutation(np.concatenate(train_indices))
    val_index = rng.permutation(np.concatenate(val_indices))

    x_train = x[train_index]
    y_train = y[train_index]
    x_val = x[val_index]
    y_val = y[val_index]

    mean = x_train.mean(axis=0)
    std = x_train.std(axis=0)
    std = np.where(std == 0, 1.0, std)

    x_train = (x_train - mean) / std
    x_val = (x_val - mean) / std

    return SplitData(
        x_train=x_train,
        y_train=y_train,
        x_val=x_val,
        y_val=y_val,
        feature_names=features.columns.tolist(),
        classes=class_names,
        mean=mean,
        std=std,
    )


def train_softmax_model(client_run, split: SplitData, *, epochs: int = 25, learning_rate: float = 0.1) -> dict:
    n_features = split.x_train.shape[1]
    n_classes = len(split.classes)
    weights = np.zeros((n_features, n_classes), dtype=np.float64)
    bias = np.zeros(n_classes, dtype=np.float64)

    y_train_one_hot = np.eye(n_classes)[split.y_train]

    for epoch in range(1, epochs + 1):
        train_logits = split.x_train @ weights + bias
        train_probabilities = softmax(train_logits)
        train_loss = cross_entropy(train_probabilities, split.y_train)
        train_accuracy = accuracy(train_logits, split.y_train)

        grad_logits = (train_probabilities - y_train_one_hot) / len(split.x_train)
        grad_weights = split.x_train.T @ grad_logits
        grad_bias = grad_logits.sum(axis=0)

        weights -= learning_rate * grad_weights
        bias -= learning_rate * grad_bias

        val_logits = split.x_val @ weights + bias
        val_accuracy = accuracy(val_logits, split.y_val)

        client_run.log_metrics(
            {
                "train_loss": train_loss,
                "train_accuracy": train_accuracy,
                "val_accuracy": val_accuracy,
            },
            step=epoch,
        )

    final_val_logits = split.x_val @ weights + bias
    final_val_accuracy = accuracy(final_val_logits, split.y_val)

    return {
        "model_type": "softmax_regression",
        "weights": weights.tolist(),
        "bias": bias.tolist(),
        "classes": split.classes,
        "feature_names": split.feature_names,
        "mean": split.mean.tolist(),
        "std": split.std.tolist(),
        "validation_accuracy": final_val_accuracy,
    }


def predict_with_downloaded_model(model_artifact: dict, features: np.ndarray) -> np.ndarray:
    weights = np.asarray(model_artifact["weights"], dtype=np.float64)
    bias = np.asarray(model_artifact["bias"], dtype=np.float64)
    mean = np.asarray(model_artifact["mean"], dtype=np.float64)
    std = np.asarray(model_artifact["std"], dtype=np.float64)
    standardized = (features - mean) / std
    logits = standardized @ weights + bias
    return logits.argmax(axis=1)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> None:
    base_url = os.getenv("MLDLC_BASE_URL", "http://localhost:8000")
    username = require_env("MLDLC_USERNAME")
    api_key = require_env("MLDLC_API_KEY")

    run_suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid4().hex[:8]
    dataset_name = f"iris-dataset-{run_suffix}"
    experiment_name = f"iris-experiment-{run_suffix}"
    repository_name = f"iris-models-{run_suffix}"
    model_name = "iris-softmax"
    model_version = "1.0"

    client = MLDLC(username=username, api_key=api_key, base_url=base_url)
    try:
        iris = fetch_iris_from_internet()
        uploaded_dataset = client.upload_dataset(
            dataset_name,
            iris,
            labels={"source": "uci", "dataset": "iris", "example": "full-lifecycle"},
        )
        downloaded_dataset = client.download_dataset(uploaded_dataset.slug, uploaded_dataset.version)
        pd.testing.assert_frame_equal(
            downloaded_dataset.reset_index(drop=True),
            iris.reset_index(drop=True),
            check_dtype=False,
        )

        experiment = client.create_experiment(
            experiment_name,
            metrics=["train_loss", "train_accuracy", "val_accuracy"],
            labels={"dataset_slug": uploaded_dataset.slug, "example": "full-lifecycle"},
        )
        repository = client.create_repository(
            repository_name,
            labels={"dataset_slug": uploaded_dataset.slug, "example": "full-lifecycle"},
        )

        split = prepare_training_data(iris)
        with client.start_run(
            experiment.slug,
            dataset=uploaded_dataset,
            labels={"stage": "training", "example": "full-lifecycle"},
        ) as run:
            model_artifact = train_softmax_model(run, split, epochs=25, learning_rate=0.1)
            uploaded_model = run.log_model(
                repository.slug,
                model_name,
                model_version,
                model_artifact,
                labels={"algorithm": "softmax_regression", "example": "full-lifecycle"},
            )

        run_info = client.get_run(experiment.slug, 1)
        train_loss_history = client.get_run_metric_history(experiment.slug, run_info.run_number, "train_loss")
        val_accuracy_history = client.get_experiment_metric_history(experiment.slug, "val_accuracy")
        downloaded_model = client.download_model(
            repository.slug,
            uploaded_model.version,
            loader=lambda path: pickle.loads(path.read_bytes()),
        )

        assert run_info.status == "COMPLETED"
        assert run_info.dataset is not None
        assert run_info.dataset.dataset_slug == uploaded_dataset.slug
        assert run_info.model is not None
        assert run_info.model.repository_slug == repository.slug
        assert uploaded_model.status == "READY"
        assert len(train_loss_history) == 25
        assert train_loss_history["step"].tolist() == list(range(1, 26))
        assert len(val_accuracy_history[val_accuracy_history["run_number"] == run_info.run_number]) == 25

        val_predictions = predict_with_downloaded_model(downloaded_model, split.x_val * split.std + split.mean)
        restored_val_accuracy = float((val_predictions == split.y_val).mean())
        assert abs(restored_val_accuracy - downloaded_model["validation_accuracy"]) < 1e-9

        recorded_datasets = client.list_datasets()
        recorded_models = client.list_models(repository.slug)
        assert any(
            item.slug == uploaded_dataset.slug and item.version == uploaded_dataset.version
            for item in recorded_datasets
        )
        assert any(item.version == uploaded_model.version and item.status == "READY" for item in recorded_models)

        print("Lifecycle finished successfully.")
        print(f"Dataset: {uploaded_dataset.slug} v{uploaded_dataset.version}")
        print(f"Experiment: {experiment.slug}")
        print(f"Run: #{run_info.run_number} status={run_info.status}")
        print(f"Repository: {repository.slug}")
        print(f"Model: {uploaded_model.name} v{uploaded_model.version} status={uploaded_model.status}")
        print(f"Recorded train_loss points: {len(train_loss_history)}")
        print(f"Recorded val_accuracy points: {len(val_accuracy_history)}")
        print(f"Validation accuracy from downloaded model: {restored_val_accuracy:.4f}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
