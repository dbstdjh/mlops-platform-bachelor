# MLDLC SDK

```python
import pandas as pd

from mldlc import MLDLC

client = MLDLC(
    username="user@example.com",
    api_key="mlp_abc123_secret",
    base_url="http://localhost:8000",
)

dataset = client.upload_dataset(
    "training-data",
    pd.DataFrame({"feature": [1, 2], "target": [0, 1]}),
)

experiment = client.create_experiment("baseline", metrics=["loss", "accuracy"])

with client.start_run(experiment.slug, dataset=dataset) as run:
    run.log_metric("loss", 0.8, step=0)
    run.log_metrics({"loss": 0.4, "accuracy": 0.9}, step=1)
    run.log_model("baseline-models", "baseline", "1.0", {"weights": [1, 2, 3]})

downloaded = client.download_dataset(dataset.slug, dataset.version)
```

## Running The Examples

All example scripts expect these environment variables:

```bash
export MLDLC_USERNAME="user@example.com"
export MLDLC_API_KEY="mlp_abc123_secret"
export MLDLC_BASE_URL="http://localhost:8000"
```

Run them from the `sdk/` directory:

```bash
uv run python examples/iris_lifecycle.py
```

Or from the repository root through `make`:

```bash
make sdk-examples
make sdk-example-multi-run-comparison
```

Each script creates unique dataset, experiment, and repository names, so you can rerun them to populate the UI with more data.

## Example Gallery

- `examples/iris_lifecycle.py`
  Full end-to-end dataset, experiment, run, and model lifecycle on the Iris dataset.
- `examples/multi_run_comparison.py`
  Creates one experiment with several runs, varied labels, different learning curves, and a mix of runs with and without attached models.
- `examples/dense_metrics_per_step.py`
  Logs many metrics at every step so you can inspect how a busy run page looks when charts and latest metrics are dense.
- `examples/long_history_batched_steps.py`
  Logs a long run history with `run.log_batch(...)`, many steps, and explicit timestamps to exercise the step-history UI.
- `examples/detached_model_workflows.py`
  Demonstrates finishing a run without logging a model inside the run, then uploading one model linked afterward and another model with no run attached at all.

## Suggested UI Walkthrough

- Start with `multi_run_comparison.py` to populate an experiment overview with multiple runs.
- Run `dense_metrics_per_step.py` to see how the run detail page handles lots of metrics.
- Run `long_history_batched_steps.py` to inspect charts with long step histories.
- Run `detached_model_workflows.py` to compare linked and unlinked model versions in the registry and run pages.
