from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


MODEL_NAME = "custom-image-demo"
MODEL_VERSION = "1.0.0"
HOST = "0.0.0.0"
PORT = 8000


class ModelHandler(BaseHTTPRequestHandler):
    server_version = "MLDLCCustomImageDemo/1.0"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"status": "ok"})
            return
        if self.path == "/ready":
            self._json(200, {"ready": True, "model": MODEL_NAME, "version": MODEL_VERSION})
            return
        self._json(404, {"detail": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/predict":
            self._json(404, {"detail": "Not found"})
            return

        try:
            payload = self._read_json()
            instances = self._extract_instances(payload)
            scores = [round(sum(float(value) for value in row), 6) for row in instances]
            predictions = ["high" if score >= 10.0 else "low" for score in scores]
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"detail": str(exc)})
            return

        self._json(
            200,
            {
                "model": MODEL_NAME,
                "version": MODEL_VERSION,
                "predictions": predictions,
                "scores": scores,
            },
        )

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("Request body is required")
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        return payload

    def _extract_instances(self, payload: dict[str, Any]) -> list[list[float]]:
        raw_instances = payload.get("instances", payload.get("features"))
        if not isinstance(raw_instances, list) or not raw_instances:
            raise ValueError("Payload must include a non-empty 'instances' or 'features' list")

        instances: list[list[float]] = []
        for item in raw_instances:
            if not isinstance(item, list) or not item:
                raise ValueError("Each instance must be a non-empty list of numbers")
            instances.append([float(value) for value in item])
        return instances

    def _json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), ModelHandler)
    print(f"Serving {MODEL_NAME} {MODEL_VERSION} on {HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
