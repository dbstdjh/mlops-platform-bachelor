# Agent Verification Criteria

When contributing to this platform, any AI agent (or developer) must adhere to the following mandatory verification criteria before finalizing their work:

## 1. Comprehensive Test Coverage
After implementing new features, modifying existing code, or resolving bugs, you **must** write automated tests for your changes. Testing is not optional and must span multiple levels:
- **Unit Tests:** Verify individual functions, business logic, and isolated components (e.g., testing the core domain entities or utility functions).
- **Integration Tests:** Ensure that different system modules and external infrastructure interact correctly (e.g., testing the FastAPI Control Plane's interaction with PostgreSQL or MinIO webhooks).
- **End-to-End (E2E) Tests:** Validate the full user journey from start to finish (e.g., triggering a model deployment via the SDK and verifying the final state through the Go Edge Gateway).

## 2. Scope of Testing
Your test suite must be resilient and cover:
- **Normal (Happy Path) Cases:** Ensuring the feature performs exactly as intended under standard conditions.
- **Edge Cases & Error Handling:** You must explicitly test failure modes. This includes invalid inputs, network timeouts, unauthenticated requests, and specific platform edge cases like "Zombie Runs" or out-of-memory (OOM) scenarios.

## 3. Strict Documentation Alignment
All tests must strictly follow the architectural patterns and workflows outlined in the `docs/` directory. For example:
- Dataset upload tests must simulate the direct-to-storage **Pre-signed URL** workflow, ensuring large payloads bypass the Control Plane.
- Deployment tests must validate the **asynchronous, event-driven** nature of the Deployment Service rather than expecting synchronous API blocking.
- Metrics tests must validate that resources adhere to the strict key-value metadata isolation.

## 4. Execution and Self-Verification
Writing the tests is only half the requirement. You **must** execute the test suite yourself in your environment to verify your work.
- If any test fails, you must actively debug and resolve the issue before concluding your task.
- You must use the terminal to run these tests and confirm they pass successfully as the final self-verification step of your workflow.
