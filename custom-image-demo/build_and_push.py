from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from mldlc import MLDLC

DEMO_DIR = Path(__file__).resolve().parent
ROOT = DEMO_DIR.parent


def load_demo_env() -> None:
    demo_env = DEMO_DIR / ".env"
    if demo_env.exists():
        load_dotenv(demo_env, override=True)
        return
    load_dotenv(ROOT / "sdk" / ".env")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def run(command: list[str], *, input_text: str | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, input=input_text, text=True, check=True)


def run_best_effort(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, text=True, check=False)


def build_client() -> MLDLC:
    return MLDLC(
        username=require_env("MLDLC_USERNAME"),
        api_key=require_env("MLDLC_API_KEY"),
        base_url=os.getenv("MLDLC_BASE_URL", "http://api.mldlc.local"),
    )


def main() -> None:
    load_demo_env()

    image_name = os.getenv("MLDLC_CUSTOM_IMAGE_NAME", "custom-image-demo")
    image_tag = os.getenv("MLDLC_CUSTOM_IMAGE_TAG", "latest")
    image_platform = os.getenv("MLDLC_CUSTOM_IMAGE_PLATFORM", "linux/amd64")
    token_name = os.getenv(
        "MLDLC_REGISTRY_TOKEN_NAME",
        f"docker-push-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
    )

    client = build_client()
    try:
        status = client.enable_custom_deployments()
        if not status.enabled or not status.username:
            raise RuntimeError("Artifact registry did not become enabled")

        token = os.getenv("MLDLC_REGISTRY_TOKEN")
        if token:
            print("Using MLDLC_REGISTRY_TOKEN from the environment.")
        else:
            issued = client.create_registry_token(token_name)
            token = issued.token
            print(f"Created registry token '{issued.name}'. Plaintext will not be stored by the platform.")

        registry_host = status.registry_host
        username = status.username
        remote_ref = f"{registry_host}/{username}/{image_name}:{image_tag}"

        run_best_effort(["docker", "logout", registry_host])
        run(["docker", "login", registry_host, "-u", username, "--password-stdin"], input_text=f"{token}\n")
        run([
            "docker",
            "buildx",
            "build",
            "--platform",
            image_platform,
            "--provenance=false",
            "--sbom=false",
            "--push",
            "-t",
            remote_ref,
            str(DEMO_DIR),
        ])

        print("\nPushed custom image:")
        print(remote_ref)
        print("\nDeploy it with:")
        print(f"MLDLC_CUSTOM_IMAGE_NAME={image_name} MLDLC_CUSTOM_IMAGE_TAG={image_tag} "
              "uv run python deploy_image.py")
    finally:
        client.close()


if __name__ == "__main__":
    main()
