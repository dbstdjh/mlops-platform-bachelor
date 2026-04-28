# Platform Overview

This MLOps platform is designed to provide a cohesive, end-to-end environment for managing the machine learning lifecycle. Everything in the platform is treated as a **resource**, utilizing a consistent key-value metadata system that allows flexible storage and filtering for any entity (e.g., storing hyperparameters for a training run). 

All primary keys for these resources are generated purely on the server-side, ensuring data integrity. The system leverages a monorepo structure.

## Core Modules

- **Users and IAM:** Handles authentication and authorization. It manages secure access across the platform, including API key issuance and JWT mechanisms.
- **Experiment Tracking:** Captures metrics during model training. It groups single executions as "runs" and aggregates related runs into "experiments" to solve specific problems.
- **Model Versioning & Registry:** A repository system for storing model artifacts. Models are preserved here and can be intrinsically linked to the runs that produced them.
- **Feature Registry:** A data repository for datasets. It manages versioned datasets (supporting formats like Pandas, Numpy, CSV, Parquet) and links them to training runs.
- **Model Serving & Deployment:** Handles the transition of model artifacts to live endpoints. It supports deploying raw model files (Pickle/Keras) or custom images, and monitors deployment statuses.
- **Model Monitoring & Observability:** Provides comprehensive dashboarding and metric plotting to observe models both during training and after deployment.
- **Artifact Registry:** Interacts with external container registries to securely manage user images.

## Core Workflows

### 1. Experiment Tracking Workflow
The platform provides a strict lifecycle for tracking model training to ensure data consistency and avoid orphaned states.
1. A **Model Repository** is created (optional).
2. An **Experiment** is defined, specifying the metrics to track and how they should be aggregated for display (e.g., sum, average). A model repository can be connected at this stage.
3. A **Run** is started under the experiment.
4. During training, the specified metrics are logged continuously.
5. If a model repository was connected, the resulting model weights or files are uploaded to it.
6. The dashboard aggregates all metrics across runs for the experiment, allowing users to drill down into the history of metric evolution for individual runs.
7. If a model was uploaded, it is visually linked to the specific run that generated it within the dashboard.

### 2. Feature Registry (Dataset) Workflow
The platform is designed to handle large datasets seamlessly without overwhelming the central API.
- **Pushing Data:** A user initiates an upload from their environment (e.g., a Jupyter Notebook). The system provisions a secure, temporary pathway for the data to be streamed directly to storage. Once the storage provider confirms the receipt of the file, the dataset's status is automatically marked as ready for use.
- **Pulling Data:** When a user requests a dataset, the system verifies the latest available version and generates a temporary, cryptographically signed pathway. The data is then ingested directly into the user's environment, completely bypassing the main API to ensure high performance and zero bottlenecks.

### 3. Model Deployment Workflow
Deployments are entirely driven through the SDK to maintain a single source of truth.
1. The user specifies the model (either a file or a Docker image) and its input/output schema.
2. The control plane validates the configuration and issues an event-driven task to the deployment service.
3. The deployment service pulls the necessary artifacts, configures the environment, and deploys the model.
4. The system monitors the deployment status asynchronously, ensuring the endpoint becomes active and healthy.
