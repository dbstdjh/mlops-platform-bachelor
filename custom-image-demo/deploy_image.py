from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from mldlc import DeploymentInfo, MLDLC


DEMO_DIR = Path(__file__).resolve().parent
ROOT = DEMO_DIR.parent
TERMINAL_FAILURE_STATUSES = {"FAILED", "DELETED"}
FeatureVector = Annotated[list[float], Field(min_length=3, max_length=3)]


def load_demo_env() -> None:
    demo_env = DEMO_DIR / ".env"
    if demo_env.exists():
        load_dotenv(demo_env, override=True)
        return
    load_dotenv(ROOT / "sdk" / ".env")


class DemoImageInput(BaseModel):
    instances: list[FeatureVector] = Field(min_length=1, examples=[[[2.5, 4.0, 6.0]]])


class DemoImageOutput(BaseModel):
    model: str
    version: str
    predictions: list[str]
    scores: list[float]


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_client() -> MLDLC:
    return MLDLC(
        username=require_env("MLDLC_USERNAME"),
        api_key=require_env("MLDLC_API_KEY"),
        base_url=os.getenv("MLDLC_BASE_URL", "http://api.mldlc.local"),
        ready_timeout=float(os.getenv("MLDLC_READY_TIMEOUT_SECONDS", "120")),
        poll_interval=float(os.getenv("MLDLC_POLL_INTERVAL_SECONDS", "2")),
    )


def make_deployment_name(image_name: str, image_tag: str) -> str:
    configured = os.getenv("MLDLC_CUSTOM_DEPLOYMENT_NAME")
    if configured:
        return configured
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    suffix = uuid4().hex[:8]
    safe_tag = image_tag.replace(".", "-").replace("_", "-")
    return f"{image_name}-{safe_tag}-{timestamp}-{suffix}"


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
    load_demo_env()

    image_name = os.getenv("MLDLC_CUSTOM_IMAGE_NAME", "custom-image-demo")
    image_tag = os.getenv("MLDLC_CUSTOM_IMAGE_TAG", "latest")
    deployment_name = make_deployment_name(image_name, image_tag)
    timeout_seconds = float(os.getenv("MLDLC_DEPLOY_TIMEOUT_SECONDS", "300"))
    poll_interval_seconds = float(os.getenv("MLDLC_DEPLOY_POLL_INTERVAL_SECONDS", "5"))

    client = build_client()
    try:
        status = client.enable_custom_deployments()
        if not status.enabled:
            raise RuntimeError("Artifact registry is not enabled")

        images = client.list_custom_images()
        pushed_image = next((image for image in images if image.name == image_name), None)
        if pushed_image is None or not any(tag.tag == image_tag for tag in pushed_image.tags):
            raise RuntimeError(
                f"Image tag '{image_name}:{image_tag}' is not visible in the artifact registry. "
                "Run custom-image-demo/build_and_push.py first."
            )

        deployment = client.deploy_image(
            image_name,
            image_tag,
            deployment_name,
            input_schema=DemoImageInput,
            output_schema=DemoImageOutput,
            labels={"example": "custom-image-demo", "image": image_name, "tag": image_tag},
        )
        active = wait_for_active_deployment(
            client,
            deployment.slug,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )

        print("\nCustom image deployment finished successfully.")
        print(f"Image: {active.image_ref}")
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
        "--data '{\"instances\":[[2.5,4.0,6.0],[1.0,1.5,2.0]]}'"
    )


if __name__ == "__main__":
    main()
