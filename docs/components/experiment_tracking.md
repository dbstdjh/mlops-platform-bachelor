# Experiment Tracking & Registry

The Experiment Tracking module allows for metric logging during model training. It works in tandem with the Model Registry to preserve both the metadata of an execution and the resulting artifact.

## Core Abstractions
- **Run:** A scope for a single execution and the set of metrics extracted during that execution.
- **Experiment:** A grouping of similar runs, typically attempting to solve the same problem or optimize the same model.
- **Repository (Model Registry):** A logical grouping of model versions. Different versions of the same model reside within a single repository.

## State Management: The "Zombie Run" Problem
A critical aspect of the tracking system is its strict state machine.

**The Flaw:** If a training script crashes mid-execution (e.g., due to a CUDA out-of-memory error), a run that was marked as "started" might never finish. Without proper handling, the dashboard becomes cluttered with "Zombie Runs" that perpetually appear to be training.

**The Fix:** A run strictly transitions through a state machine: `RUNNING` -> `COMPLETED` or `FAILED`. The Python SDK wraps the user's training loop in a robust `try/catch` block to guarantee that failures are intercepted and explicitly reported back to the API.

## Tracking Workflow Details
1. A **model repository** can be created to house artifacts.
2. An **experiment** is created. The user specifies which metrics to log and how they should be aggregated on the dashboard.
3. A **run** is initiated and transitions to `RUNNING`.
4. During the training loop, the metrics defined in the experiment are logged via the SDK. *(Note: If a metric defined in the experiment is not logged by the user's script, it is considered the user's responsibility).*
5. If a model repository was associated with the run, the model weights or serialized files (`.pkl` or `.keras`) are uploaded.
6. A successful completion transitions the run to `COMPLETED`.
7. **Dashboard Integration:** The run is visually linked to the uploaded model. Future runs linked to the same repository will generate new model versions.
