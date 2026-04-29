"""
Unit tests for core domain entities.
These test the pure domain layer — no database, no external services.
"""

import uuid
import pytest
from src.core.entities.resource import Resource, ResourceCreate
from src.core.entities.experiment_tracking import (
    Experiment,
    ExperimentCreate,
    Run,
    RunCreate,
    RunRef,
    RunStepBatchCreate,
)
from src.core.entities.model_repository import ModelRepository, ModelRepositoryCreate
from src.core.entities.model import Model, ModelCreate
from src.core.entities.dataset import Dataset, DatasetCreate


class TestResourceEntity:
    def test_resource_has_default_id(self):
        r = Resource()
        assert r.id is not None
        assert isinstance(r.id, uuid.UUID)

    def test_resource_has_empty_labels_by_default(self):
        r = Resource()
        assert r.labels == {}

    def test_resource_with_labels(self):
        labels = {"env": "staging", "team": "ml"}
        r = Resource(labels=labels)
        assert r.labels == labels

    def test_resource_create_schema(self):
        data = ResourceCreate(labels={"key": "value"})
        assert data.labels == {"key": "value"}


class TestModelRepositoryEntity:
    def test_model_repository_defaults(self):
        user_id = uuid.uuid4()
        resource_id = uuid.uuid4()
        repo = ModelRepository(user_id=user_id, resource_id=resource_id, name="test-repo", slug="test-repo")
        assert repo.name == "test-repo"
        assert repo.slug == "test-repo"
        assert repo.is_deleted is False
        assert repo.created_at is not None

    def test_model_repository_create_schema(self):
        data = ModelRepositoryCreate(name="housing-predictor", labels={"type": "regression"})
        assert data.name == "housing-predictor"
        assert data.labels == {"type": "regression"}


class TestModelEntity:
    def test_model_defaults(self):
        model = Model(
            resource_id=uuid.uuid4(),
            repository_id=uuid.uuid4(),
            name="housing-model",
            version="1.0",
        )
        assert model.is_deleted is False
        assert model.s3_uri is None
        assert model.run_id is None
        assert model.status == "PENDING"
        assert model.file_type == "undefined"

    def test_model_create_schema(self):
        data = ModelCreate(
            name="housing-model",
            version="2.0",
            run=RunRef(experiment_slug="training", run_number=3),
            labels={"framework": "keras"},
        )
        assert data.version == "2.0"
        assert data.run is not None
        assert data.run.run_number == 3


class TestDatasetEntity:
    def test_dataset_defaults(self):
        dataset = Dataset(
            user_id=uuid.uuid4(),
            resource_id=uuid.uuid4(),
            name="housing-prices",
            slug="housing-prices",
        )
        assert dataset.status == "PENDING"
        assert dataset.version == 1
        assert dataset.file_type is None

    def test_dataset_create_schema(self):
        data = DatasetCreate(name="iris", file_type="csv")
        assert data.name == "iris"
        assert data.file_type == "csv"
        assert data.labels == {}


class TestExperimentTrackingEntities:
    def test_experiment_defaults(self):
        experiment = Experiment(
            user_id=uuid.uuid4(),
            resource_id=uuid.uuid4(),
            name="vision",
            slug="vision",
            logged_data_template=["loss"],
        )
        assert experiment.slug == "vision"
        assert experiment.logged_data_template == ["loss"]

    def test_experiment_create_deduplicates_template(self):
        data = ExperimentCreate(
            name="vision",
            logged_data_template=["loss", "loss", " accuracy ", ""],
        )
        assert data.logged_data_template == ["loss", "accuracy"]

    def test_run_defaults(self):
        run = Run(
            resource_id=uuid.uuid4(),
            experiment_id=uuid.uuid4(),
            number=1,
        )
        assert run.status == "RUNNING"
        assert run.ended_at is None

    def test_run_create_requires_complete_dataset_ref(self):
        with pytest.raises(ValueError):
            RunCreate(dataset_slug="events")

    def test_run_step_batch_requires_metrics(self):
        with pytest.raises(ValueError):
            RunStepBatchCreate(items=[{"step": 1, "logged_data": {}}])
