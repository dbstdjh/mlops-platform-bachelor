from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from sklearn_pickle_server.config import Settings


class ModelLoadError(RuntimeError):
    pass


class InputNormalizationError(ValueError):
    pass


class PredictionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelBundle:
    model: Any
    model_path: Path
    model_type: str


def load_model(model_path: Path) -> ModelBundle:
    if not model_path.exists():
        raise ModelLoadError(f"Model artifact not found at {model_path}")
    if not model_path.is_file():
        raise ModelLoadError(f"Model artifact path is not a file: {model_path}")

    try:
        model = joblib.load(model_path)
    except Exception as joblib_error:
        try:
            with model_path.open("rb") as handle:
                model = pickle.load(handle)
        except Exception as pickle_error:
            raise ModelLoadError(
                f"Could not load model with joblib or pickle: {pickle_error}"
            ) from joblib_error

    return ModelBundle(
        model=model,
        model_path=model_path,
        model_type=f"{type(model).__module__}.{type(model).__name__}",
    )


def normalize_input(payload: Any, settings: Settings) -> Any:
    extracted = _extract_payload(payload, settings.input_key)

    if settings.input_mode == "raw":
        return extracted
    if settings.input_mode == "array":
        return _as_array(extracted)
    if settings.input_mode == "dataframe":
        return _as_dataframe(extracted)
    return _auto_normalize(extracted)


def predict(model: Any, model_input: Any, method_name: str) -> Any:
    try:
        if method_name == "call":
            if not callable(model):
                raise PredictionError("Configured model is not callable")
            return model(model_input)

        method = getattr(model, method_name, None)
        if method is None or not callable(method):
            raise PredictionError(f"Model does not expose callable '{method_name}'")
        return method(model_input)
    except PredictionError:
        raise
    except Exception as exc:
        raise PredictionError(f"Model inference failed: {exc}") from exc


def to_jsonable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return to_jsonable(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.DataFrame):
        return to_jsonable(value.to_dict(orient="records"))
    if isinstance(value, pd.Series):
        return to_jsonable(value.tolist())
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    return value


def _extract_payload(payload: Any, input_key: str | None) -> Any:
    if payload is None:
        raise InputNormalizationError("Request body must be a JSON object, array, or scalar")

    if input_key is not None:
        if not isinstance(payload, dict):
            raise InputNormalizationError("MLDLC_INPUT_KEY requires a JSON object request body")
        if input_key not in payload:
            raise InputNormalizationError(f"Request body is missing configured key '{input_key}'")
        return payload[input_key]

    if isinstance(payload, dict):
        for key in ("instances", "inputs", "data", "features"):
            if key in payload:
                return payload[key]

    return payload


def _auto_normalize(value: Any) -> Any:
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        return _as_dataframe(value)
    if isinstance(value, dict):
        return _as_dataframe(value)
    return _as_array(value)


def _as_array(value: Any) -> np.ndarray:
    if value is None:
        raise InputNormalizationError("Array input cannot be null")
    if isinstance(value, (dict, pd.DataFrame)):
        raise InputNormalizationError("Array input cannot be a JSON object")

    array = np.asarray(value)
    if array.size == 0:
        raise InputNormalizationError("Array input cannot be empty")
    if array.ndim == 0:
        return array.reshape(1, 1)
    if array.ndim == 1:
        return array.reshape(1, -1)
    return array


def _as_dataframe(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        frame = value
    elif isinstance(value, list):
        if not value:
            raise InputNormalizationError("DataFrame input cannot be empty")
        if not all(isinstance(item, dict) for item in value):
            raise InputNormalizationError("DataFrame list input must contain objects")
        frame = pd.DataFrame(value)
    elif isinstance(value, dict):
        if not value:
            raise InputNormalizationError("DataFrame input cannot be empty")
        if all(_is_sequence(item) for item in value.values()):
            frame = pd.DataFrame(value)
        else:
            frame = pd.DataFrame([value])
    else:
        raise InputNormalizationError("DataFrame input must be an object or list of objects")

    if frame.empty or len(frame.columns) == 0:
        raise InputNormalizationError("DataFrame input cannot be empty")
    return frame


def _is_sequence(value: Any) -> bool:
    if isinstance(value, (str, bytes, bytearray, dict)):
        return False
    return isinstance(value, (list, tuple, np.ndarray, pd.Series))
