from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


@pytest.mark.parametrize(
    "file_name",
    [
        "iris_lifecycle.py",
        "multi_run_comparison.py",
        "dense_metrics_per_step.py",
        "long_history_batched_steps.py",
        "detached_model_workflows.py",
        "deploy_pickle_model.py",
    ],
)
def test_example_modules_import_without_running(file_name: str):
    path = EXAMPLES_DIR / file_name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert callable(module.main)
