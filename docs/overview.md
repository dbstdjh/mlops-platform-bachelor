# Platform Overview

> [!IMPORTANT]
> **Project Context: Bachelor's Thesis**
> This project is a **Bachelor's Thesis**. The goal is to build a focused, high-quality Proof-of-Concept MLOps platform. 
> **Agent Instructions:** Do not introduce enterprise-scale bloat, unnecessary microservices, or over-engineered abstractions. However, you must still write clean, robust, and highly intelligent code. Strictly follow the established architectural patterns (e.g., onion architecture, event-driven workflows) and maintain technical excellence without over-complicating the scope.


This MLOps platform is designed to provide a cohesive, end-to-end environment for managing the machine learning lifecycle. Everything in the platform is treated as a **resource**, utilizing a consistent key-value metadata system that allows flexible storage and filtering for any entity (e.g., storing hyperparameters for a training run). 

All primary keys for these resources are generated purely on the server-side, ensuring data integrity. The system leverages a monorepo structure.

## System Components

The platform is composed of several custom-developed applications and services working in tandem:

### 1. Control Plane API (FastAPI)
A monolithic backend built with a strict onion architecture (core, application, infrastructure, presentation). It serves as the primary entry point for platform administration. It consists of the following core modules:
- **Users and IAM:** Handles authentication, authorization, API key issuance, and JWT mechanisms.
- **Experiment Tracking:** Captures metrics during model training, managing "runs" and grouping them into "experiments".
- **Model Versioning & Registry:** A repository system for storing model artifacts linked to training runs.
- **Feature Registry:** Manages versioned datasets (Pandas DataFrames, Numpy arrays, CSV and Parquet files).
- **Model Serving & Deployment Module:** Validates configurations and triggers the deployment service.
- **Model Monitoring & Observability:** Manages dashboard generation and metric plotting via embedded Grafana iframes.
- **Artifact Registry:** Interacts with the Gitea API to securely manage user container images.

### 2. Python SDK
The primary interface for data scientists to interact with the platform. It handles Control Plane API interactions, orchestrates direct-to-storage data uploads (bypassing the API to avoid OOM issues), wraps training loops to enforce strict state machine reporting, and initiates deployments.

### 3. Web App Dashboard (React + Tailwind CSS)
A heavily read-optimized UI dedicated to observability. It provides a visual interface to explore experiments, datasets, and deployed models. It features embedded plotting capabilities for both run details and deployment metrics.

### 4. Deployment Service (Python)
An event-driven worker responsible for materializing models into the Kubernetes cluster. It is triggered via PostgreSQL's `LISTEN/NOTIFY` mechanism when the Control Plane inserts a deployment task. Upon receiving the signal, it claims the task, pulls the necessary Docker images or model files, and provisions the cluster resources. After deployment, it polls the Kubernetes API for pod health to confirm the endpoint is active.

### 5. Edge API Gateway (Go)
A high-performance proxy that intercepts all inference traffic heading to deployed models. It validates JWT authentication, securely routes traffic to the Minikube cluster, and logs request/response payloads to PostgreSQL for model drift monitoring.

### 6. Model Containers & Images
The execution environments for user models. The system supports deploying models via pre-built base images designed to load raw artifacts (`.pickle` or `.keras` files), or by pulling fully custom user-built Docker images from the Artifact Registry.

## Core Workflows

### 1. Experiment Tracking Workflow
The platform provides a strict lifecycle for tracking model training to ensure data consistency and avoid orphaned states.
1. A **Model Repository** is created (optional).
2. An **Experiment** is defined, specifying the metrics to track. A model repository can be connected at this stage.
3. A **Run** is started under the experiment.
4. During training, the specified metrics are logged continuously.
5. If a model artifact was uploaded during the run, it is placed into the specified model repository.
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
