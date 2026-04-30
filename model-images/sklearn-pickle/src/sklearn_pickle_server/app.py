from __future__ import annotations

from contextlib import asynccontextmanager
from json import JSONDecodeError

from fastapi import FastAPI, HTTPException, Request, status

from sklearn_pickle_server.config import Settings
from sklearn_pickle_server.model_runtime import (
    InputNormalizationError,
    ModelBundle,
    ModelLoadError,
    PredictionError,
    load_model,
    normalize_input,
    predict,
    to_jsonable,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_settings = settings or Settings.from_env()
        app.state.settings = resolved_settings
        app.state.model_bundle = None
        app.state.load_error = None

        try:
            app.state.model_bundle = load_model(resolved_settings.model_path)
        except (ModelLoadError, ValueError) as exc:
            app.state.load_error = str(exc)

        yield

    app = FastAPI(
        title="MLDLC Scikit-Learn Pickle Server",
        description="Global prebuilt inference server for scikit-learn pickle artifacts.",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        bundle = _get_bundle(app)
        return {
            "status": "ready",
            "model_path": str(bundle.model_path),
            "model_type": bundle.model_type,
        }

    @app.post("/predict")
    async def predict_route(request: Request):
        bundle = _get_bundle(app)
        request_settings: Settings = app.state.settings

        try:
            payload = await request.json()
        except JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request body must be valid JSON",
            ) from exc

        try:
            model_input = normalize_input(payload, request_settings)
            output = predict(bundle.model, model_input, request_settings.predict_method)
        except InputNormalizationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        except PredictionError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc

        return {request_settings.response_key: to_jsonable(output)}

    return app


def _get_bundle(app: FastAPI) -> ModelBundle:
    bundle = app.state.model_bundle
    if bundle is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=app.state.load_error or "Model is not loaded",
        )
    return bundle


app = create_app()
