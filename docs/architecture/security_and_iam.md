# Security and IAM

The Users and IAM module manages authentication and authorization for the entire platform. To decouple concerns, the platform utilizes the **FastAPI Users** library.

## API Gateway Authentication
While FastAPI Users handles the core logic, JWT validation for model endpoints is performed at the edge by the **Go API Gateway**. This keeps the underlying service layers pure and prevents unauthorized traffic from ever reaching the model containers.

## Enterprise Secret Management (Gitea)
The platform integrates tightly with Gitea to manage Artifact Registries (Docker images) for users. Exposing Gitea's God-level Admin token directly to user workflows is an unacceptable security risk.

To solve this, the platform implements the **Per-Tenant Encrypted Service Principal** pattern. This utilizes two distinct types of tokens:

### 1. The "Backend Proxy Token" (Encrypted)
- **Creation:** When a user registers, FastAPI uses the Global Admin Token *exactly once* to create the user inside Gitea and generate a Proxy Token for them.
- **Storage:** FastAPI encrypts this token using a symmetric key (AES-256 or Fernet) and stores the ciphertext in the PostgreSQL database (`user_feature_config` column).
- **Usage:** This token is completely invisible to the user. FastAPI decrypts it in-memory strictly to perform administrative actions on the user's behalf (e.g., listing their Docker images or generating temporary CLI tokens).

### 2. The "CLI Tokens" (User Managed)
- **Creation:** When a user requests a new token in the UI, FastAPI decrypts the Proxy Token and securely asks Gitea to generate a new CLI token.
- **Storage:** FastAPI **never** stores this token. Gitea stores the hash, and FastAPI merely catches the plain-text response, displays it to the user exactly once in the React UI, and immediately forgets it.
- **Usage:** The user uses this plain-text token in their local terminal for actions like `docker login`.
